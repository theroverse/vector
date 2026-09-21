"""Quarentena do Vector: na GUI nada e apagado - pastas sao MOVIDAS para um
backup unico .vec (zip auto-contido com manifesto) e podem voltar de la.

Politica (spec 2026-09-21): guarda apenas a ULTIMA execucao; seal()
substitui o backup anterior. restaurar do backup ATIVO = move de volta e
enxuga a entrada; restaurar de .vec EXTERNO = copia, o arquivo nao muda.

Formato .vec: zip ZIP_DEFLATED com manifest.json na raiz + itens sob
"<id>/<pasta-arquivo>/...". O manifesto carrega os metadados de decisao
(kind/confidence/sensitive/label/summaryPlain/original/tamanho) para a tela
de Restauracao funcionar em qualquer maquina, sem re-scan.

Recuperacao de queda: stage() grava um <id>.meta.json por item no staging;
se o processo morreu antes do seal(), o primeiro inspect() sela o que existe.
Itens nunca se perdem.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from vector.models import OrphanCandidate
from vector.scoring import plain_summary

ACTIVE_NAME = "last.vec"
MANIFEST_NAME = "manifest.json"
_STAGING = "staging"


def root(base: Optional[Path] = None) -> Path:
    """Pasta da quarentena. Testes injetam base (tmp_path); runtime usa LOCALAPPDATA."""
    if base is not None:
        return Path(base)
    local = os.environ.get("LOCALAPPDATA")
    parent = Path(local) / "Vector" if local else Path.home() / ".vector"
    return parent / "quarantine"


def active_path(base: Optional[Path] = None) -> Path:
    return root(base) / ACTIVE_NAME


def _entry_json(entry: dict) -> str:
    return json.dumps(entry, ensure_ascii=False)


def stage(candidate: OrphanCandidate,
          base: Optional[Path] = None) -> tuple[Optional[dict], str]:
    """Move a pasta inteira para o staging. Devolve (entrada, "") ou (None, motivo)."""
    src = Path(candidate.path)
    if not src.exists():
        return None, "a pasta nao existe mais (ja foi removida em outra limpeza?)"
    rid = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    entry = {
        "id": rid,
        "original": str(src),
        "archived": src.name,
        "sizeBytes": candidate.size_bytes,
        "ts": int(time.time()),
        "kind": candidate.kind,
        "confidence": candidate.confidence,
        "sensitive": candidate.sensitive,
        "label": candidate.label,
        "summaryPlain": plain_summary(candidate),
    }
    dst = root(base) / _STAGING / rid / src.name
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        (root(base) / _STAGING / f"{rid}.meta.json").write_text(
            _entry_json(entry), encoding="utf-8")
    except PermissionError:
        return None, "sem permissao para mover esta pasta (rode como admin)."
    except OSError as exc:
        return None, f"falha ao mover: {exc}"
    return entry, ""


def _read_staged(base: Optional[Path]) -> list[tuple[dict, Path]]:
    """(entrada, pasta_do_item) de tudo que espera no staging, ordenado por ts."""
    staging = root(base) / _STAGING
    if not staging.exists():
        return []
    out = []
    for meta in sorted(staging.glob("*.meta.json")):
        entry = json.loads(meta.read_text(encoding="utf-8"))
        out.append((entry, staging / entry["id"]))
    out.sort(key=lambda t: t[0]["ts"])
    return out


def seal(base: Optional[Path] = None) -> Optional[dict]:
    """Compacta o staging em last.vec, SUBSTITUINDO o backup anterior.

    Devolve o inspect() resultante, ou None se nao havia nada selado.
    Falha nunca apaga o staging (os itens ja movidos se preservam).
    """
    staged = _read_staged(base)
    if not staged:
        shutil.rmtree(root(base) / _STAGING, ignore_errors=True)
        return None
    entries = [e for e, _ in staged]
    target = active_path(base)
    tmp = target.with_name(ACTIVE_NAME + ".tmp")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry, folder in staged:
                for f in sorted((folder / entry["archived"]).rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(folder).as_posix())
            zf.writestr(MANIFEST_NAME, _entry_json(
                {"sealed_ts": int(time.time()), "items": entries}))
        if target.exists():
            target.unlink()
        tmp.replace(target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"falha ao selar a quarentena: {exc}")
    shutil.rmtree(root(base) / _STAGING, ignore_errors=True)
    return inspect(base=base)


def _read_vec(path: Path) -> Optional[dict]:
    try:
        with zipfile.ZipFile(path) as zf:
            return json.loads(zf.read(MANIFEST_NAME))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, OSError):
        return None


def _is_external(path: Path, base: Optional[Path]) -> bool:
    try:
        return Path(path).resolve() != active_path(base).resolve()
    except OSError:
        return True


def inspect(path: Optional[Path] = None,
            base: Optional[Path] = None) -> Optional[dict]:
    """Le um .vec (default: o ativo). Staging orfao (queda no meio de uma
    execucao) e selado no primeiro acesso - itens nunca se perdem."""
    if path is None:
        if _read_staged(base):
            return seal(base=base)
        target = active_path(base)
    else:
        target = Path(path)
    if not target.exists():
        return None
    manifest = _read_vec(target)
    if manifest is None:
        return {"file": str(target), "corrupt": True, "items": [],
                "external": _is_external(target, base)}
    return {
        "file": str(target),
        "external": _is_external(target, base),
        "sealedTs": manifest["sealed_ts"],
        "fileBytes": target.stat().st_size,
        "totalBytes": sum(i.get("sizeBytes", 0) for i in manifest["items"]),
        "items": manifest["items"],
    }
