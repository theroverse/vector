"""Bridge de fase 2: servidor JSON-lines que expoe o motor ao VectorHost.ps1.

Protocolo (uma mensagem JSON por linha; stdin = pedidos, stdout = respostas):

    -> {"id": 1, "cmd": "scan", "target": "Notion"}
    <- {"id": 1, "ok": true, "result": <report payload camelCase>}

    -> {"id": 2, "cmd": "remove", "path": "C:\\...\\Pasta"}
    <- {"id": 2, "ok": true, "result": {"removed": true, "detail": "...", "path": ...}}

    -> {"id": 3, "cmd": "ping"}
    <- {"id": 3, "ok": true, "result": {"app": "vector", "phase": "engine", ...}}

O relatorio da ultima varredura fica EM MEMORIA (BridgeState.report). O comando
`remove` so aceita um caminho que o PROPRIO motor pontuou como cleanable
(HIGH/MEDIUM), do tipo folder e nao-allowlisted. A digitacao literal + confirmacao
da GUI sao UX; o gate de seguranca real esta aqui, reusando as mesmas regras do
vector-cli.py --clean. Nada de seguranca e reimplementado em JS/PowerShell.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Callable, Optional, TextIO

from vector import __version__
from vector.models import OrphanCandidate, ScanReport
from vector.report import to_report_payload
from vector.settings import CLEANABLE_CONFIDENCES
from vector.utils import is_allowlisted


@dataclass
class BridgeState:
    """Estado de longa duracao do processo: o ultimo relatorio pontuado."""

    report: Optional[ScanReport] = None


def _default_scan(target: Optional[str] = None) -> ScanReport:
    from vector import engine

    return engine.run_scan(target=target)


def _default_remove(path: str) -> tuple[bool, str]:
    from vector.cleaner import _remove_folder

    return _remove_folder(path)


def _authorize(state: BridgeState, path: str) -> tuple[Optional[OrphanCandidate], str]:
    """Confere o caminho contra o relatorio em memoria. (candidato, motivo_negativo)."""
    if state.report is None:
        return None, "Rode uma varredura antes de remover qualquer item."
    candidate = next(
        (c for c in state.report.candidates if c.path == path), None)
    if candidate is None:
        return None, "Este caminho nao esta na ultima varredura; varra de novo."
    if candidate.kind != "folder":
        return None, ("Registro, servicos e tarefas nunca sao removidos pelo "
                      "Vector: use o comando manual.")
    if candidate.confidence not in CLEANABLE_CONFIDENCES:
        return None, f"Candidato {candidate.confidence} nunca e oferecido para remocao."
    if is_allowlisted(candidate.label, candidate.path):
        return None, "Caminho protegido pela allowlist (sistema/drivers)."
    return candidate, ""


def handle_request(
    request: dict,
    state: BridgeState,
    *,
    scan_fn: Optional[Callable[..., ScanReport]] = None,
    remove_fn: Optional[Callable[[str], tuple[bool, str]]] = None,
) -> dict:
    """Despacha um pedido e devolve a resposta (envelope {id, ok, result|error}).

    scan_fn/remove_fn sao injetaveis para teste; padrao = motor real.
    """
    req_id = request.get("id")
    cmd = request.get("cmd")

    if cmd == "ping":
        return _ok(req_id, {"app": "vector", "phase": "engine",
                            "version": __version__})

    if cmd == "scan":
        scan = scan_fn or _default_scan
        target = request.get("target") or None
        try:
            report = scan(target=target)
        except Exception as exc:  # noqa: BLE001 - fronteira: nunca derrubar o host
            return _err(req_id, f"Falha na varredura: {exc}")
        state.report = report
        return _ok(req_id, to_report_payload(report))

    if cmd == "remove":
        path = request.get("path") or ""
        candidate, refusal = _authorize(state, path)
        if candidate is None:
            return _err(req_id, refusal)
        remove = remove_fn or _default_remove
        try:
            removed, detail = remove(candidate.path)
        except Exception as exc:  # noqa: BLE001
            return _err(req_id, f"Falha ao remover: {exc}")
        return _ok(req_id, {"removed": removed, "detail": detail,
                            "path": candidate.path})

    return _err(req_id, f"Comando desconhecido: {cmd!r}")


def _ok(req_id, result: dict) -> dict:
    return {"id": req_id, "ok": True, "result": result}


def _err(req_id, error: str) -> dict:
    return {"id": req_id, "ok": False, "error": error}


def serve(
    inp: Optional[TextIO] = None,
    out: Optional[TextIO] = None,
    *,
    scan_fn: Optional[Callable[..., ScanReport]] = None,
    remove_fn: Optional[Callable[[str], tuple[bool, str]]] = None,
) -> None:
    """Loop principal: le uma linha JSON por vez ate o EOF, responde em stdout."""
    src = inp if inp is not None else sys.stdin
    dst = out if out is not None else sys.stdout
    state = BridgeState()
    for line in src:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _err(None, f"JSON invalido: {exc}")
        else:
            response = handle_request(request, state,
                                      scan_fn=scan_fn, remove_fn=remove_fn)
        dst.write(json.dumps(response, ensure_ascii=False) + "\n")
        dst.flush()
