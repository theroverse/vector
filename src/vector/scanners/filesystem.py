"""Scanner de filesystem: Program Files, AppData, ProgramData, Temp."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from vector.models import Evidence, OrphanCandidate
from vector.settings import (
    FILESYSTEM_ROOT_ENV_VARS,
    NEAR_EMPTY_THRESHOLD,
    SHARED_FOLDER_HINTS,
    STALE_DAYS,
    UNINSTALLER_HINTS,
    WEIGHT_LEFTOVER_UNINSTALLER,
    WEIGHT_NAME_NOT_INSTALLED,
    WEIGHT_STALE_OR_EMPTY,
)
from vector.utils import name_matches, normalize_name


@dataclass
class FsScanResult:
    candidates: list[OrphanCandidate]
    roots_scanned: list[str]
    access_denied: list[str]


def resolve_roots() -> list[Path]:
    """Resolve as raizes via variaveis de ambiente; ignora as ausentes."""
    roots: list[Path] = []
    for var in FILESYSTEM_ROOT_ENV_VARS:
        value = os.environ.get(var)
        if value and Path(value).is_dir():
            roots.append(Path(value))
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _is_link(path: Path) -> bool:
    """Junction ou symlink (no Windows, junction NAO e symlink)."""
    try:
        if path.is_symlink():
            return True
    except (PermissionError, OSError):
        return False
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            return bool(is_junction())
        except (PermissionError, OSError):
            return False
    return False


def safe_iterdir(path: Path, access_denied: list[str]) -> list[Path]:
    """Lista filhos tratando PermissionError de forma elegante."""
    try:
        # Junctions/symlinks do Windows (ex.: "Dados de Aplicativos",
        # "Menu Iniciar" em ProgramData) apontam para locais ja varridos
        # ou protegidos — pular evita duplicatas e falsos-positivos.
        if _is_link(path):
            return []
        return [entry for entry in path.iterdir() if not _is_link(entry)]
    except PermissionError:
        access_denied.append(f"{path} (sem permissao de leitura)")
        return []
    except OSError as exc:
        access_denied.append(f"{path} (erro de acesso: {exc.strerror or exc})")
        return []


def safe_stat_size_mtime(path: Path) -> tuple[int, float | None]:
    """Soma tamanho/mtime de 1 nivel; falhas retornam parcial."""
    total = 0
    newest: float | None = None
    try:
        entries = list(path.iterdir())
    except (PermissionError, OSError):
        return 0, None
    for entry in entries:
        try:
            stat = entry.stat()
            newest = stat.st_mtime if newest is None else max(newest, stat.st_mtime)
            if entry.is_file():
                total += stat.st_size
        except (PermissionError, OSError):
            continue
    return total, newest


def _has_leftover_uninstaller(children_names: set[str]) -> str | None:
    for hint in UNINSTALLER_HINTS:
        if hint in children_names:
            return hint
    return None



def scan_filesystem(
    installed: set[str],
    target: str | None = None,
    roots: list[Path] | None = None,
) -> FsScanResult:
    """Cruza pastas das raizes contra o inventario e gera candidatos."""
    wanted = normalize_name(target) if target else None
    search_roots = roots if roots is not None else resolve_roots()
    # TEMP e cache volatil: so vira candidato com evidencia extra
    # (abandono/resto de desinstalador). Quando `roots` e injetado
    # (testes), a regra nao se aplica — o teste controla o cenario.
    using_real_roots = roots is None
    candidates: list[OrphanCandidate] = []
    access_denied: list[str] = []
    roots_scanned = [str(r) for r in search_roots]
    now = time.time()

    for root in search_roots:
        for child in safe_iterdir(root, access_denied):
            # Junctions do Windows (Documentos, Desktop, Menu Iniciar em
            # ProgramData; "Dados de Aplicativos" etc.) sao links para locais
            # fora das raizes ou ja varridos — pula sem virar candidato.
            if _is_link(child):
                continue
            try:
                is_dir = child.is_dir()
            except (PermissionError, OSError):
                access_denied.append(f"{child} (sem permissao de leitura)")
                continue
            if not is_dir:
                continue

            normalized = normalize_name(child.name)
            if wanted and wanted not in normalized and normalized not in wanted:
                continue
            if not wanted and any(hint in normalized for hint in SHARED_FOLDER_HINTS):
                continue  # infra compartilhada: nunca candidata sozinha

            # TEMP e cache volatil: so vira candidato com evidencia extra.
            is_temp = using_real_roots and "temp" in str(root).lower()
            evidences: list[Evidence] = []
            if not name_matches(normalized, installed) and not is_temp:
                evidences.append(
                    Evidence(
                        description="+40 nome ausente nos programas instalados",
                        weight=WEIGHT_NAME_NOT_INSTALLED,
                        source="filesystem",
                    )
                )

            children = safe_iterdir(child, access_denied)
            children_names = {c.name.lower() for c in children}

            leftover = _has_leftover_uninstaller(children_names)
            if leftover:
                evidences.append(
                    Evidence(
                        description=f"+15 resta {leftover} sem entrada de desinstalacao",
                        weight=WEIGHT_LEFTOVER_UNINSTALLER,
                        source="filesystem",
                    )
                )

            size_bytes, mtime = safe_stat_size_mtime(child)
            age_days: int | None = None
            if mtime is not None:
                age_days = int((now - mtime) // 86400)
                if age_days >= STALE_DAYS:
                    evidences.append(
                        Evidence(
                            description=f"+10 pasta abandonada ({age_days} dias parada)",
                            weight=WEIGHT_STALE_OR_EMPTY,
                            source="filesystem",
                        )
                    )
            elif not children:
                evidences.append(
                    Evidence(
                        description="+10 pasta vazia ou ilegivel",
                        weight=WEIGHT_STALE_OR_EMPTY,
                        source="filesystem",
                    )
                )

            if not evidences:
                continue

            candidates.append(
                OrphanCandidate(
                    kind="folder",
                    path=str(child),
                    label=child.name,
                    evidences=evidences,
                    size_bytes=size_bytes,
                    age_days=age_days,
                )
            )

    return FsScanResult(
        candidates=candidates,
        roots_scanned=roots_scanned,
        access_denied=access_denied,
    )
