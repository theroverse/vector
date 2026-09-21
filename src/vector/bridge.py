"""Bridge de fase 2: servidor JSON-lines que expoe o motor ao VectorHost.ps1.

Protocolo (uma mensagem JSON por linha; stdin = pedidos, stdout = respostas):

    -> {"id": 1, "cmd": "scan", "target": "Notion"}
    <- {"id": 1, "ok": true, "result": <report payload camelCase>}

    -> {"id": 2, "cmd": "remove", "path": "C:\\...\\Pasta"}
    <- {"id": 2, "ok": true, "result": {"removed": true, "quarantined": true,
                                        "id": "<entry>", "detail": "..."}}

    -> {"id": 3, "cmd": "ping"}
    <- {"id": 3, "ok": true, "result": {"app": "vector", "phase": "engine", ...}}

    -> {"cmd": "quarantine-seal"} | {"cmd": "quarantine-inspect"}
    -> {"cmd": "quarantine-restore", "id": "<entry>"}   ("id" E o id do item)
    -> {"cmd": "quarantine-purge"} | {"cmd": "quarantine-export", "dest": ...}
    -> {"cmd": "backup-inspect", "path": "C:\\\\...\\\\last.vec"}
    -> {"cmd": "backup-restore", "path": ..., "id": "<entry>"}

O relatorio da ultima varredura fica EM MEMORIA (BridgeState.report). O comando
`remove` so aceita um caminho que o PROPRIO motor pontuou como cleanable
(HIGH/MEDIUM), do tipo folder e nao-allowlisted - e MOVE para a quarentena
(vector.quarantine), nunca apaga. A digitacao literal + confirmacao da GUI
sao UX; o gate de seguranca real esta aqui, reusando as mesmas regras do
vector-cli.py --clean. Nada de seguranca e reimplementado em JS/PowerShell.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, TextIO

from vector import __version__
from vector.models import OrphanCandidate, ScanReport
from vector.report import to_report_payload
from vector.settings import CLEANABLE_CONFIDENCES
from vector.utils import is_allowlisted


@dataclass
class BridgeState:
    """Estado de longa duracao do processo: o ultimo relatorio pontuado e a
    raiz da quarentena (None = LOCALAPPDATA; teste injeta tmp_path)."""

    report: Optional[ScanReport] = None
    base: Optional[Path] = None


def _default_scan(target: Optional[str] = None) -> ScanReport:
    from vector import engine

    return engine.run_scan(target=target)


def _default_stage(candidate, base: Optional[Path] = None):
    from vector import quarantine

    return quarantine.stage(candidate, base=base)


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
    stage_fn: Optional[Callable[..., tuple[Optional[dict], str]]] = None,
) -> dict:
    """Despacha um pedido e devolve a resposta (envelope {id, ok, result|error}).

    scan_fn/stage_fn sao injetaveis para teste; padrao = motor real.
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
        stage = stage_fn or _default_stage
        try:
            entry, fail = stage(candidate, base=state.base)
        except Exception as exc:  # noqa: BLE001
            return _err(req_id, f"Falha ao mover para a quarentena: {exc}")
        if entry is None:
            return _ok(req_id, {"removed": False, "quarantined": False,
                                "path": path, "detail": fail})
        return _ok(req_id, {"removed": True, "quarantined": True, "path": path,
                            "id": entry["id"], "sizeBytes": entry["sizeBytes"],
                            "detail": "movida para a quarentena"})

    if cmd in ("quarantine-seal", "quarantine-inspect", "quarantine-purge",
               "quarantine-restore", "quarantine-export",
               "backup-inspect", "backup-restore"):
        return _quarantine(req_id, cmd, request, state)

    return _err(req_id, f"Comando desconhecido: {cmd!r}")


def _quarantine(req_id, cmd: str, request: dict,
                state: BridgeState) -> dict:
    """Comandos de quarentena/backup. No restore o campo "id" do pedido E o
    id do item - o host e sincronico (uma linha fora, uma linha dentro)."""
    from vector import quarantine

    path = Path(request["path"]) if request.get("path") else None
    dest = Path(request["dest"]) if request.get("dest") else None
    entry_id = request.get("id") or ""
    if isinstance(entry_id, int):  # so o id RPC, nao um id de item
        entry_id = ""
    try:
        if cmd == "quarantine-seal":
            info = quarantine.seal(base=state.base)
            return _ok(req_id, info or {"sealedTs": None, "items": []})
        if cmd == "quarantine-inspect":
            info = quarantine.inspect(base=state.base)
            return _ok(req_id, info or {"file": None, "items": []})
        if cmd == "quarantine-restore":
            ok, detail = quarantine.restore_one(entry_id, base=state.base)
            return _ok(req_id, {"restored": ok, "moved": True, "detail": detail})
        if cmd == "quarantine-purge":
            return _ok(req_id, {"purged": quarantine.purge(base=state.base)})
        if cmd == "quarantine-export":
            if not dest:
                return _err(req_id, "falta o destino da copia.")
            ok, detail = quarantine.export(dest, base=state.base)
            return _ok(req_id, {"exported": ok, "detail": detail})
        if cmd == "backup-inspect":
            if not path:
                return _err(req_id, "falta o caminho do .vec.")
            info = quarantine.inspect(path=path, base=state.base)
            return _ok(req_id, info or {"file": None, "items": []})
        if cmd == "backup-restore":
            if not path:
                return _err(req_id, "falta o caminho do .vec.")
            ok, detail = quarantine.restore_one(entry_id, path=path,
                                                base=state.base)
            return _ok(req_id, {"restored": ok, "moved": False, "detail": detail})
    except Exception as exc:  # noqa: BLE001 - fronteira
        return _err(req_id, f"Quarentena: {exc}")
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
    stage_fn: Optional[Callable[..., tuple[Optional[dict], str]]] = None,
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
                                      scan_fn=scan_fn, stage_fn=stage_fn)
        dst.write(json.dumps(response, ensure_ascii=False) + "\n")
        dst.flush()
