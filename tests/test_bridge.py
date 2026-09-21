"""Bridge de fase 2: protocolo JSON-lines e o gate de remocao em memoria.

remove agora move para a quarentena (stage_fn injetavel); comandos
quarantine-*/backup-* exercitam o vector.quarantine real com base em tmp.
"""

import json
import shutil

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

    def stage_fn(candidate, base=None):
        calls.append(candidate.path)
        return {"id": "z1", "sizeBytes": 5}, ""

    resp = bridge.handle_request(
        {"id": 4, "cmd": "remove", "path": r"C:\App\Good"}, state,
        stage_fn=stage_fn)
    assert resp["ok"] is True
    assert resp["result"]["removed"] is True
    assert resp["result"]["quarantined"] is True
    assert calls == [r"C:\App\Good"]


def test_remove_low_confidence_refused():
    state = bridge.BridgeState(report=_report())
    resp = bridge.handle_request(
        {"id": 5, "cmd": "remove", "path": r"C:\App\Weak"}, state,
        stage_fn=lambda cand, base=None: ({"id": "x", "sizeBytes": 1}, ""))
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
        state, stage_fn=lambda cand, base=None: ({"id": "x", "sizeBytes": 1}, ""))
    assert resp["ok"] is False


def test_remove_reports_failure_detail():
    state = bridge.BridgeState(report=_report())
    resp = bridge.handle_request(
        {"id": 9, "cmd": "remove", "path": r"C:\App\Good"}, state,
        stage_fn=lambda cand, base=None: (None, "sem permissao (rode como admin)"))
    assert resp["ok"] is True
    assert resp["result"]["removed"] is False
    assert resp["result"]["quarantined"] is False
    assert "admin" in resp["result"]["detail"]


def test_remove_result_marks_quarantined():
    state = bridge.BridgeState(report=_report())
    resp = bridge.handle_request(
        {"id": 9, "cmd": "remove", "path": r"C:\App\Good"}, state,
        stage_fn=lambda cand, base=None: ({"id": "abc", "sizeBytes": 10}, ""))
    assert resp["ok"] and resp["result"]["quarantined"] is True
    assert resp["result"]["id"] == "abc"


def test_unknown_command():
    state = bridge.BridgeState()
    resp = bridge.handle_request({"id": 10, "cmd": "reboot"}, state)
    assert resp["ok"] is False


def test_serve_reads_lines_writes_lines():
    inp = json.dumps({"id": 1, "cmd": "ping"}) + "\n"
    out = _StringOut()
    bridge.serve(inp=iter(inp.splitlines()), out=out)
    assert json.loads(out.value)["result"]["app"] == "vector"


# ---------------- quarentena real pela bridge (base = tmp_path) -------------

def _victim(tmp_path, name):
    """Pasta real que o stage vai MOV ER + report pontuando ela como HIGH."""
    d = tmp_path / "vitima" / name
    d.mkdir(parents=True)
    (d / "a.txt").write_text("x", encoding="utf-8")
    return ScanReport(target=None, installed_count=1,
                      candidates=[_folder(str(d), name, "HIGH")]), d


def test_quarantine_inspect_empty_returns_items_list(tmp_path):
    state = bridge.BridgeState(base=tmp_path / "q")
    resp = bridge.handle_request({"id": 10, "cmd": "quarantine-inspect"}, state)
    assert resp["ok"] and resp["result"]["items"] == []


def test_quarantine_flow_stage_seal_restore_purge(tmp_path):
    report, d = _victim(tmp_path, "GoodApp")
    state = bridge.BridgeState(report=report, base=tmp_path / "q")
    r = bridge.handle_request({"id": 11, "cmd": "remove", "path": str(d)}, state)
    assert r["result"]["removed"] and r["result"]["quarantined"]
    assert not d.exists()
    r = bridge.handle_request({"id": 12, "cmd": "quarantine-seal"}, state)
    assert r["ok"] and r["result"]["sealedTs"]
    r = bridge.handle_request({"id": 13, "cmd": "quarantine-inspect"}, state)
    item = r["result"]["items"][0]
    # no restore o campo "id" do pedido E o id do item (host e sincrono)
    r = bridge.handle_request({"cmd": "quarantine-restore", "id": item["id"]}, state)
    assert r["ok"] and r["result"]["restored"] is True
    assert d.exists() and (d / "a.txt").exists()
    r = bridge.handle_request({"id": 15, "cmd": "quarantine-purge"}, state)
    assert r["ok"] and r["result"]["purged"] is False  # vec sumiu no ultimo restore


def test_backup_inspect_and_restore_external(tmp_path):
    report, d = _victim(tmp_path, "ExtApp")
    state = bridge.BridgeState(report=report, base=tmp_path / "q")
    bridge.handle_request({"id": 1, "cmd": "remove", "path": str(d)}, state)
    bridge.handle_request({"id": 2, "cmd": "quarantine-seal"}, state)
    copy = tmp_path / "fora.vec"
    shutil.copyfile(tmp_path / "q" / "last.vec", copy)
    r = bridge.handle_request({"id": 3, "cmd": "backup-inspect",
                               "path": str(copy)}, state)
    assert r["ok"] and r["result"]["external"] is True
    item = r["result"]["items"][0]
    r = bridge.handle_request({"cmd": "backup-restore", "id": item["id"],
                               "path": str(copy)}, state)
    assert r["ok"] and r["result"]["restored"] and r["result"]["moved"] is False
    assert d.exists()
    # externo e backup, nao lixeira: a copia de fora mantem o item
    r = bridge.handle_request({"id": 4, "cmd": "backup-inspect",
                               "path": str(copy)}, state)
    assert len(r["result"]["items"]) == 1


def test_quarantine_export_via_bridge(tmp_path):
    report, d = _victim(tmp_path, "CopyApp")
    state = bridge.BridgeState(report=report, base=tmp_path / "q")
    bridge.handle_request({"id": 1, "cmd": "remove", "path": str(d)}, state)
    bridge.handle_request({"id": 2, "cmd": "quarantine-seal"}, state)
    dest = tmp_path / "cp" / "meu.vec"
    r = bridge.handle_request({"id": 5, "cmd": "quarantine-export",
                               "dest": str(dest)}, state)
    assert r["ok"] and r["result"]["exported"] and dest.exists()


def test_bridge_unknown_quarantine_cmd_still_errors(tmp_path):
    state = bridge.BridgeState(base=tmp_path / "q")
    resp = bridge.handle_request({"id": 16, "cmd": "quarantine-teleport"}, state)
    assert not resp["ok"]


class _StringOut:
    def __init__(self):
        self.value = ""

    def write(self, text):
        self.value += text

    def flush(self):
        pass
