"""Scanner de servicos: ImagePath que aponta para executavel inexistente."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from vector.models import Evidence, OrphanCandidate
from vector.settings import WEIGHT_NAME_NOT_INSTALLED, WEIGHT_ORPHAN_SERVICE_TASK
from vector.utils import normalize_name

_IMAGE_PATH_RE = re.compile(r"ImagePath\s*:\s*(.+)", re.IGNORECASE)


def _extract_binary(image_path: str) -> str:
    text = image_path.strip().strip('"')
    # "C:\\app\\svc.exe -k run" -> "C:\\app\\svc.exe"
    match = re.match(r'"([^"]+)"|(\S+)', text)
    candidate = (match.group(1) or match.group(2)) if match else text
    return candidate.strip().strip('"')


def scan_services(
    installed: set[str],
    target: str | None = None,
    runner=None,
) -> tuple[list[OrphanCandidate], list[str]]:
    """Lista servicos via `sc query` e confere o binario com `sc qc`."""
    wanted = normalize_name(target) if target else None
    run = runner or (lambda cmd: subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", shell=False))
    if shutil.which("sc") is None:
        return [], ["Comando 'sc' indisponivel: scanner de servicos pulado."]

    try:
        result = run(["sc", "query", "type=", "service", "state=", "all"])
        output = result.stdout or ""
    except (OSError, PermissionError) as exc:
        return [], [f"Falha ao listar servicos ({exc}); scanner pulado."]

    candidates: list[OrphanCandidate] = []
    warnings: list[str] = []
    for line in output.splitlines():
        if "SERVICE_NAME" not in line:
            continue
        svc_name = line.split(":", 1)[1].strip()
        normalized = normalize_name(svc_name)
        if wanted and wanted not in normalized and normalized not in wanted:
            continue
        try:
            qc = run(["sc", "qc", svc_name])
            qc_out = qc.stdout or ""
        except (OSError, PermissionError):
            warnings.append(f"Sem acesso a configuracao de '{svc_name}'.")
            continue
        match = _IMAGE_PATH_RE.search(qc_out)
        if not match:
            continue
        binary = _extract_binary(match.group(1))
        if not binary or ":" not in binary or Path(binary).exists():
            continue
        evidences = [Evidence(
            description=f"+20 servico aponta p/ executavel inexistente ({binary})",
            weight=WEIGHT_ORPHAN_SERVICE_TASK, source="services")]
        if normalized not in installed:
            evidences.append(Evidence(
                description="+40 servico sem programa correspondente instalado",
                weight=WEIGHT_NAME_NOT_INSTALLED, source="services"))
        candidates.append(OrphanCandidate(
            kind="service", path=svc_name, label=svc_name, evidences=evidences,
            manual_command=f'sc delete "{svc_name}"  (pare o servico antes; revise!)',
        ))
    return candidates, warnings
