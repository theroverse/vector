"""Inventario de programas INSTALADOS — a fonte de verdade do cruzamento.

Le as chaves Uninstall do Registro (HKLM + HKCU, incluindo WOW6432Node)
e devolve nomes normalizados. Fora do Windows, devolve conjunto vazio com
aviso (permite testar/rodar o resto do pipeline em qualquer SO).
"""

from __future__ import annotations

from pathlib import Path

from vector.utils import normalize_name

UNINSTALL_PATHS = (
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
)


def _read_value(key, name: str) -> str:
    try:
        import winreg

        value, _ = winreg.QueryValueEx(key, name)
        return str(value).strip() if value else ""
    except OSError:
        return ""


def _read_uninstall_entries(root_name: str, sub_path: str) -> list[tuple[str, str]]:
    """Le (DisplayName, InstallLocation|DisplayIcon) de cada subchave."""
    try:
        import winreg
    except ImportError:
        return []

    roots = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}
    entries: list[tuple[str, str]] = []
    try:
        with winreg.OpenKey(roots[root_name], sub_path) as base:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(base, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(base, subkey_name) as subkey:
                        display = _read_value(subkey, "DisplayName")
                        location = _read_value(subkey, "InstallLocation")
                        if not location:
                            icon = _read_value(subkey, "DisplayIcon")
                            location = icon.split(",")[0].strip().strip('"')
                        if display:
                            entries.append((display, location))
                except OSError:
                    continue
    except (OSError, PermissionError):
        return entries
    return entries


def _read_uninstall_key(root_name: str, sub_path: str) -> list[str]:
    """Compat: so DisplayName (mantido para testes existentes)."""
    return [name for name, _ in _read_uninstall_entries(root_name, sub_path)]


def get_installed_programs() -> tuple[set[str], list[str]]:
    """Retorna (nomes_normalizados, avisos).

    O conjunto contem nomes normalizados via normalize_name(), prontos para
    comparacao com pastas/servicos/tarefas suspeitas. Alem do DisplayName,
    inclui o nome-base do InstallLocation/DisplayIcon ("C:\\...\\Docker"
    -> "docker"), cobrindo programas cujo DisplayName difere da pasta
    (ex.: "Docker Desktop" instalado na pasta "Docker").
    """
    warnings: list[str] = []
    try:
        import winreg  # noqa: F401
    except ImportError:
        warnings.append("Registro indisponivel (nao-Windows): inventario vazio.")
        return set(), warnings

    installed: set[str] = set()
    for root_name, sub_path in UNINSTALL_PATHS:
        for name, location in _read_uninstall_entries(root_name, sub_path):
            normalized = normalize_name(name)
            if normalized:
                installed.add(normalized)
            if location:
                base = Path(str(location)).name.strip()
                if base:
                    installed.add(normalize_name(base))
    return installed, warnings
