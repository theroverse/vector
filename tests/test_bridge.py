"""Bridge de fase 2: protocolo JSON-lines e o gate de remocao em memoria."""

import json

from vector import bridge
from vector.models import Evidence, OrphanCandidate, ScanReport


def _folder(path, label, confidence, score=50):
    return OrphanCandidate(
        kind="folder", path=path, label=label, score=score,
        confidence=confidence,
        evidences=[Evidence(description="+40 ausente", weight=40,
                            source="filesystem")],
    )


def _report():
    return ScanReport(
        target=None,
        installed_count=7,
        candidates=[
            _folder(r"C:\App\Good", "Good", "HIGH"),
            _folder(r"C:\App\Weak", "Weak", "LOW", score=10),
            _folder(r"C:\Program Files\Microsoft\Win", "Microsoft Win", "HIGH"),
            OrphanCandidate(kind="service", path="OldSvc", label="OldSvc",
                            confidence="HIGH", score=60,
                            evidences=[Evidence("+20 svc", 20, "services")]),
        ],
    )


def _scan_fn(installed=None):
    return lambda target=None: _report()


def test_ping():
    state = bridge.BridgeState()
    resp = bridge.handle_request({"id": 1, "cmd": "ping"}, state)
    assert resp == {"id": 1, "ok": True,
                    "result": {"app": "vector", "phase": "engine",
                               "version": bridge.__version__}}


def test_scan_stores_report_and_returns_camelcase():
    state = bridge.BridgeState()
    resp = bridge.handle_request(
        {"id": 2, "cmd": "scan", "target": None}, state, scan_fn=_scan_fn())
    assert resp["ok"] is True
    assert resp["result"]["installedCount"] == 7
    assert state.report is not None
    assert any(c["confidence"] == "HIGH" for c in resp["result"]["candidates"])


def test_remove_before_scan_is_refused():
    state = bridge.BridgeState()
    resp = bridge.handle_request(
        {"id": 3, "cmd": "remove", "path": r"C:\App\Good"}, state)
    assert resp["ok"] is False
    assert "varredura" in resp["error"].lower() or "varra" in resp["error"].lower()


def test_remove_allowed_folder():
    state = bridge.BridgeState(report=_report())
    calls = []

    def remove_fn(path):
        calls.append(path)
        return True, "pasta removida"

    resp = bridge.handle_request(
        {"id": 4, "cmd": "remove", "path": r"C:\App\Good"}, state,
        remove_fn=remove_fn)
    assert resp["ok"] is True
    assert resp["result"]["removed"] is True
    assert calls == [r"C:\App\Good"]


def test_remove_low_confidence_refused():
    state = bridge.BridgeState(report=_report())
    resp = bridge.handle_request(
        {"id": 5, "cmd": "remove", "path": r"C:\App\Weak"}, state,
        remove_fn=lambda p: (True, "nao deveria chamar"))
    assert resp["ok"] is False
    assert "LOW" in resp["error"]


def test_remove_unknown_path_refused():
    state = bridge.BridgeState(report=_report())
    resp = bridge.handle_request(
        {"id": 6, "cmd": "remove", "path": r"C:\Nao\Existe"}, state)
    assert resp["ok"] is False


def test_remove_non_folder_refused():
    state = bridge.BridgeState(report=_report())
    resp = bridge.handle_request(
        {"id": 7, "cmd": "remove", "path": "OldSvc"}, state)
    assert resp["ok"] is False
    assert "manual" in resp["error"].lower()


def test_remove_allowlisted_refused():
    state = bridge.BridgeState(report=_report())
    resp = bridge.handle_request(
        {"id": 8, "cmd": "remove", "path": r"C:\Program Files\Microsoft\Win"},
        state, remove_fn=lambda p: (True, "nao deveria"))
    assert resp["ok"] is False


def test_remove_reports_failure_detail():
    state = bridge.BridgeState(report=_report())
    resp = bridge.handle_request(
        {"id": 9, "cmd": "remove", "path": r"C:\App\Good"}, state,
        remove_fn=lambda p: (False, "sem permissao (rode como admin)"))
    assert resp["ok"] is True
    assert resp["result"]["removed"] is False
    assert "admin" in resp["result"]["detail"]


def test_unknown_command():
    state = bridge.BridgeState()
    resp = bridge.handle_request({"id": 10, "cmd": "reboot"}, state)
    assert resp["ok"] is False


def test_serve_reads_lines_writes_lines():
    inp = json.dumps({"id": 1, "cmd": "ping"}) + "\n"
    out = _StringOut()
    bridge.serve(inp=iter(inp.splitlines()), out=out)
    assert json.loads(out.value)["result"]["app"] == "vector"


class _StringOut:
    def __init__(self):
        self.value = ""

    def write(self, text):
        self.value += text

    def flush(self):
        pass
