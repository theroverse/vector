"""Scanner de Registro: chaves Uninstall/Run orfas e App Paths quebrados."""

from __future__ import annotations

from pathlib import Path

from vector.models import Evidence, OrphanCandidate
from vector.settings import (
    APP_PATHS_REG_PATH,
    RUN_REG_PATHS,
    UNINSTALL_REG_PATHS,
    WEIGHT_NAME_NOT_INSTALLED,
    WEIGHT_TARGET_MISSING,
)
from vector.utils import clean_binary, expand_windows_path, normalize_name


def _hive_handles():
    try:
        import winreg
    except ImportError:
        return None
    return winreg


def _matches_target(label: str, wanted: str | None) -> bool:
    if not wanted:
        return True
    normalized = normalize_name(label)
    return wanted in normalized or normalized in wanted


def scan_registry(installed, target=None):
    """Chaves Uninstall cujo InstallLocation nao existe + Run quebrados."""
    wanted = normalize_name(target) if target else None
    winreg = _hive_handles()
    if winreg is None:
        return [], ["Registro indisponivel (nao-Windows): scanner pulado."]
    candidates: list[OrphanCandidate] = []
    warnings: list[str] = []
    hives = ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU"))
    for sub_path in UNINSTALL_REG_PATHS:
        for hive, hive_name in hives:
            try:
                with winreg.OpenKey(hive, sub_path) as base:
                    index = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(base, index)
                        except OSError:
                            break
                        index += 1
                        cand = _check_uninstall_subkey(
                            winreg, base, subkey_name, hive_name,
                            sub_path, installed, wanted)
                        if cand is not None:
                            candidates.append(cand)
            except (OSError, PermissionError) as exc:
                warnings.append(f"Sem acesso a {hive_name}\\{sub_path}: {exc}")
    for sub_path in RUN_REG_PATHS:
        for hive, hive_name in hives:
            candidates.extend(_check_run_key(winreg, hive, hive_name, sub_path, wanted))
    candidates.extend(_check_app_paths(winreg, wanted))
    return candidates, warnings


def _check_uninstall_subkey(winreg, base, subkey_name, hive_name, sub_path,
                            installed, wanted):
    try:
        with winreg.OpenKey(base, subkey_name) as key:
            try:
                display, _ = winreg.QueryValueEx(key, "DisplayName")
            except OSError:
                return None
            label = str(display).strip() if display else subkey_name
            if not _matches_target(label, wanted):
                return None
            try:
                location, _ = winreg.QueryValueEx(key, "InstallLocation")
            except OSError:
                location = ""
            normalized = normalize_name(label)
            in_inventory = normalized in installed
            missing = bool(location) and not expand_windows_path(
                str(location)).exists()
            if in_inventory and not missing:
                return None
            # Chave sem DisplayName util ou sem nenhuma evidencia real de
            # orfandade nao vira candidato: evita centenas de LOWs vindos
            # de componentes (ex.: "Windows Driver Package", updates).
            if normalized in ("", "program", "package", "update", "driver"):
                return None
            evidences: list[Evidence] = []
            if not in_inventory:
                evidences.append(Evidence(
                    description="+40 chave sem programa correspondente instalado",
                    weight=WEIGHT_NAME_NOT_INSTALLED, source="registry"))
            if missing:
                evidences.append(Evidence(
                    description=f"+30 InstallLocation inexistente ({location})",
                    weight=WEIGHT_TARGET_MISSING, source="registry"))
            if not evidences:
                return None
            full = f"{hive_name}\\{sub_path}\\{subkey_name}"
            return OrphanCandidate(
                kind="registry", path=full, label=label, evidences=evidences,
                manual_command=f'reg delete "{full}" /f  (revise antes de executar)',
            )
    except (OSError, PermissionError):
        return None


def _check_run_key(winreg, hive, hive_name, sub_path, wanted):
    found: list[OrphanCandidate] = []
    try:
        with winreg.OpenKey(hive, sub_path) as key:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if not _matches_target(str(name), wanted):
                    continue
                binary = clean_binary(str(value))
                if binary and ":" in binary and not expand_windows_path(binary).exists():
                    full = f"{hive_name}\\{sub_path} -> {name}"
                    found.append(OrphanCandidate(
                        kind="registry", path=full, label=str(name),
                        evidences=[Evidence(
                            description="+30 Run aponta p/ binario inexistente",
                            weight=WEIGHT_TARGET_MISSING, source="registry")],
                        manual_command=f'Remova "{name}" de {hive_name}\\{sub_path} via regedit.',
                    ))
    except (OSError, PermissionError):
        pass
    return found


def _check_app_paths(winreg, wanted):
    found: list[OrphanCandidate] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, APP_PATHS_REG_PATH) as base:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(base, index)
                except OSError:
                    break
                index += 1
                if not _matches_target(subkey_name, wanted):
                    continue
                try:
                    with winreg.OpenKey(base, subkey_name) as key:
                        default, _ = winreg.QueryValueEx(key, "")
                        if default and not expand_windows_path(
                                str(default)).exists():
                            full = f"HKLM\\{APP_PATHS_REG_PATH}\\{subkey_name}"
                            found.append(OrphanCandidate(
                                kind="registry", path=full, label=subkey_name,
                                evidences=[Evidence(
                                    description=f"+30 App Path quebrado ({default})",
                                    weight=WEIGHT_TARGET_MISSING, source="registry")],
                                manual_command=f'reg delete "{full}" /f  (revise antes).',
                            ))
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return found
