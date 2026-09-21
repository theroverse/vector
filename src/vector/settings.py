"""Constantes centrais da nave Vector.

Tudo que e "conhecimento sobre o Windows" mora aqui, para que os
scanners, a pontuacao e a limpeza compartilhem a mesma fonte de verdade.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Raizes de filesystem varridas (nomes de variaveis de ambiente).
# A resolucao para caminho absoluto acontece em scanners/filesystem.py,
# que ignora com elegancia as variaveis ausentes (ex.: Linux).
# ---------------------------------------------------------------------------
FILESYSTEM_ROOT_ENV_VARS: tuple[str, ...] = (
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramData",
    "LOCALAPPDATA",
    "APPDATA",
    "TEMP",
)

# Profundidade da varredura dentro de cada raiz (1 = so filhos diretos).
# Propositalmente raso: rapido, seguro e com poucos falsos-positivos.
SCAN_DEPTH = 1

# Uma pasta e considerada "abandonada" apos tantos dias sem modificacao.
STALE_DAYS = 180

# Pastas quase vazias (<= N entradas) ganham evidencia de abandono.
NEAR_EMPTY_THRESHOLD = 3

# Nome de executaveis que indicam "resto de desinstalador".
UNINSTALLER_HINTS: tuple[str, ...] = (
    "unins000.exe",
    "unins001.exe",
    "uninstall.exe",
    "uninstaller.exe",
)

# ---------------------------------------------------------------------------
# Registro do Windows — hives de desinstalacao lidos pelo inventario e
# pelo scanner de registro.
# ---------------------------------------------------------------------------
UNINSTALL_REG_PATHS: tuple[str, ...] = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)

RUN_REG_PATHS: tuple[str, ...] = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
)

APP_PATHS_REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"

# ---------------------------------------------------------------------------
# Allowlist: nomes que NUNCA sao sugeridos para remocao, mesmo com score
# alto. Protege componentes do sistema e drivers.
# ---------------------------------------------------------------------------
ALLOWLIST_NAMES: frozenset[str] = frozenset(
    {
        "microsoft",
        "windows",
        "windows nt",
        "nvidia",
        "intel",
        "realtek",
        "amd",
        "qualcomm",
        "lenovo",
        "dell",
        "hp",
        "asus",
        "acer",
        "samsung",
        "common files",
        "arquivos comuns",
        "windowsapps",
        "microsoft.net",
        "internet explorer",
        "windowspowershell",
    }
)

# Pastas que nunca entram na lista de limpeza, mesmo se orfas.
ALLOWLIST_PATH_FRAGMENTS: tuple[str, ...] = (
    "microsoft\\windows",
    "microsoft.net",
    "common files",
    "arquivos comuns",
    "windowsapps",
    "packages\\microsoft",
    "uninstall information",
    "windows sidebar",
    "dados de aplicativos",
    "dados de aplicativos".replace(" ", ""),
)

# ---------------------------------------------------------------------------
# Padroes que indicam possivel dado sensivel. Nao zeram o score, mas marcam
# o candidato com sensitive=True e disparam alerta extra no --clean.
# ---------------------------------------------------------------------------
SENSITIVE_HINTS: tuple[str, ...] = (
    "save",
    "backup",
    "wallet",
    "carteira",
    "projeto",
    "project",
    "documento",
    ".pst",
    ".ost",
    "foto",
    "photo",
)

# Pastas compartilhadas entre varios programas: nunca sao evidencia de
# orfao sozinhas (ex.: "Common Files", "Package Cache", inferred via nome).
SHARED_FOLDER_HINTS: tuple[str, ...] = (
    "common files",
    "package cache",
    "packagemanagement",
    "reference assemblies",
    "windows kits",
    "msbuild",
    "packages",
    "publishers",
)

# ---------------------------------------------------------------------------
# Pesos de evidencia (soma transparente, exibida com -v).
# ---------------------------------------------------------------------------
WEIGHT_NAME_NOT_INSTALLED = 40
WEIGHT_TARGET_MISSING = 30
WEIGHT_ORPHAN_SERVICE_TASK = 20
WEIGHT_LEFTOVER_UNINSTALLER = 15
WEIGHT_STALE_OR_EMPTY = 10
WEIGHT_ALLOWLISTED = -100

THRESHOLD_HIGH = 70
THRESHOLD_MEDIUM = 40

# Candidate LOW nunca e oferecido no --clean (decisao de seguranca).
CLEANABLE_CONFIDENCES: frozenset[str] = frozenset({"HIGH", "MEDIUM"})

# Onde o Vector registra o que foi removido/pulado no --clean.
CLEAN_LOG_DIRNAME = ".vector"
CLEAN_LOG_FILENAME = "vector-clean.log"
