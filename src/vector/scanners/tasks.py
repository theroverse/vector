"""Scanner de tarefas agendadas: acoes que apontam para binario inexistente."""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
from pathlib import Path

from vector.models import Evidence, OrphanCandidate
from vector.settings import WEIGHT_NAME_NOT_INSTALLED, WEIGHT_ORPHAN_SERVICE_TASK
from vector.utils import normalize_name


def _task_binary(action: str) -> str:
    text = action.strip()
    if text.lower().startswith('"'):
        end = text.find('"', 1)
        return text[1:end] if end > 0 else text.strip('"')
    return text.split(" ")[0].strip().strip('"')


def scan_tasks(
    installed: set[str],
    target: str | None = None,
    runner=None,
) -> tuple[list[OrphanCandidate], list[str]]:
    """Le `schtasks /query /fo CSV /v` e confere o binario de cada acao."""
    wanted = normalize_name(target) if target else None
    run = runner or (lambda cmd: subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", shell=False))
    if shutil.which("schtasks") is None:
        return [], ["Comando 'schtasks' indisponivel: scanner de tarefas pulado."]

    try:
        result = run(["schtasks", "/query", "/fo", "CSV", "/v"])
        output = result.stdout or ""
    except (OSError, PermissionError) as exc:
        return [], [f"Falha ao listar tarefas ({exc}); scanner pulado."]

    candidates: list[OrphanCandidate] = []
    warnings: list[str] = []
    try:
        rows = list(csv.DictReader(io.StringIO(output)))
    except csv.Error as exc:
        return [], [f"CSV do schtasks ilegivel ({exc}); scanner pulado."]

    for row in rows:
        name = (row.get("TaskName") or row.get("Nome da Tarefa") or "").strip()
        action = (
            row.get("Task To Run") or row.get("Tarefa a Executar")
            or row.get("Action") or ""
        ).strip()
        if not name or not action:
            continue
        normalized = normalize_name(f"{name} {action}")
        if wanted and wanted not in normalized:
            continue
        binary = _task_binary(action)
        if not binary or ":" not in binary or Path(binary).exists():
            continue
        evidences = [Evidence(
            description=f"+20 tarefa executa binario inexistente ({binary})",
            weight=WEIGHT_ORPHAN_SERVICE_TASK, source="tasks")]
        if normalized not in installed and (wanted is None or wanted not in normalized):
            # Nome da tarefa raramente iguala o programa; so soma quando o
            # binario tambem sugere orfandade clara via pasta inexistente.
            parent = str(Path(binary).parent).lower()
            if wanted is None or wanted in parent:
                evidences.append(Evidence(
                    description="+40 tarefa sem programa correspondente",
                    weight=WEIGHT_NAME_NOT_INSTALLED, source="tasks"))
        candidates.append(OrphanCandidate(
            kind="task", path=name, label=name, evidences=evidences,
            manual_command=f'schtasks /delete /tn "{name}" /f  (revise antes!)',
        ))
    return candidates, warnings
