"""Utilidades compartilhadas: normalizacao de nomes e checagem sensivel."""

from __future__ import annotations

import os
import re
from pathlib import Path

from vector.settings import ALLOWLIST_NAMES, ALLOWLIST_PATH_FRAGMENTS, SENSITIVE_HINTS

_VERSION_RE = re.compile(r"\s+v?\d+(\.\d+)*(\s*\(.*\))?\s*$", re.IGNORECASE)
_SUFFIX_RE = re.compile(
    r"\s+(inc\.?|llc|ltd\.?|gmbh|s\.?a\.?s?|corp\.?|corporation|technologies|labs?)\.?$",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Normaliza um nome de programa/pasta para comparacao.

    "Notion 3.1 (64-bit)" -> "notion"; "Spotify LLC" -> "spotify".
    Reduz falsos-positivos no cruzamento instalado x orfao.
    """
    text = name.strip().lower().replace("_", " ").replace("-", " ")
    text = _SUFFIX_RE.sub("", text)
    text = _VERSION_RE.sub("", text)
    text = re.sub(r"\s*\(.*\)\s*$", "", text)  # "Google Chrome (x64)" -> "google chrome"
    text = re.sub(r"\s+", " ", text).strip()
    return text


def name_matches(folder_normalized: str, installed: set[str]) -> bool:
    """Cruza pasta x inventario com tolerancia a sufixos e prefixos.

    Cobre casos reais do Uninstall: "Mozilla Firefox" instalado vs pasta
    "Mozilla"; "Docker Desktop" instalado vs pasta "Docker"; "Python 3.14"
    vs pasta "Python314". So vale para nomes com >= 4 chars (evita
    "Code" casar com "VS Code"... na verdade e exatamente isso que
    queremos evitar de marcar como orfao: "Code" E parte do VS Code).
    """
    if folder_normalized in installed:
        return True
    compact_folder = folder_normalized.replace(" ", "")
    for program in installed:
        compact_program = program.replace(" ", "")
        if len(folder_normalized) < 4:
            continue
        # Pasta e prefixo/contida no programa ("docker" em "docker desktop",
        # "mozilla" em "mozilla firefox", "python314" ~ "python").
        if folder_normalized in program or program in folder_normalized:
            return True
        if compact_folder and (compact_folder in compact_program
                               or compact_program in compact_folder):
            return True
    return False


def is_allowlisted(name: str, path: str = "") -> bool:
    """True se o nome/caminho pertence a componente protegido do sistema."""
    normalized = normalize_name(name)
    if normalized in ALLOWLIST_NAMES:
        return True
    for allowed in ALLOWLIST_NAMES:
        # "microsoft visual c++ 2015" contem "microsoft": protegido.
        # "microsoft vs code" contem "microsoft" mas e app de usuario:
        # exige que o nome COMECE com o termo allowlisted.
        if normalized == allowed or normalized.startswith(allowed + " "):
            return True
    lowered_path = path.lower()
    return any(fragment in lowered_path for fragment in ALLOWLIST_PATH_FRAGMENTS)


def looks_sensitive(path: str, label: str = "") -> bool:
    """Heuristica simples de dado sensivel (backup, save, wallet, ...)."""
    haystack = f"{path}\n{label}".lower()
    return any(hint in haystack for hint in SENSITIVE_HINTS)


def expand_windows_path(raw: str) -> Path:
    """Expande %VAR% do Registro (ex.: %SystemRoot%, %ProgramFiles%)."""
    expanded = os.path.expandvars(raw.strip().strip('"'))
    return Path(expanded)


def clean_binary(raw: str) -> str:
    """Extrai o executavel de um valor Run (remove args, rundll32, etc.)."""
    text = raw.strip()
    if text.lower().startswith('"'):
        end = text.find('"', 1)
        return text[1:end] if end > 0 else text.strip('"')
    first = text.split(" ")[0].strip().strip('"')
    # rundll32.exe carrega DLLs do sistema: o binario existe, mas o alvo
    # real e a DLL — nao e evidencia de orfandade por si so.
    if first.lower().endswith("rundll32.exe"):
        return ""
    return first
