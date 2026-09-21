"""Report: arvore textual, filtro de confianca e export JSON."""

from vector.models import Evidence, OrphanCandidate, ScanReport
from vector.report import render_tree, to_report_payload, write_json


def _report():
    high = OrphanCandidate(
        kind="folder", path=r"C:\x\OldApp", label="OldApp",
        evidences=[Evidence(description="+40 ausente", weight=40, source="filesystem")],
        score=40, confidence="MEDIUM",
    )
    low = OrphanCandidate(
        kind="task", path="IdleTask", label="IdleTask",
        evidences=[Evidence(description="+10 fraca", weight=10, source="tasks")],
        score=10, confidence="LOW",
    )
    return ScanReport(target=None, candidates=[high, low], installed_count=5)


def test_tree_shows_all_by_default():
    tree = render_tree(_report())
    assert "OldApp" in tree and "IdleTask" in tree
    assert "MEDIUM" in tree and "LOW" in tree


def test_tree_min_confidence_filters():
    tree = render_tree(_report(), min_confidence="MEDIUM")
    assert "OldApp" in tree
    assert "IdleTask" not in tree


def test_tree_empty_message():
    tree = render_tree(ScanReport(target="Nada", candidates=[]))
    assert "Nenhum residuo" in tree


def test_json_export(tmp_path):
    dest = tmp_path / "rel.json"
    write_json(_report(), dest)
    import json

    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["installed_count"] == 5
    assert len(payload["candidates"]) == 2


def test_bridge_payload_is_camelcase():
    """to_report_payload espelha a forma camelCase que mock.js/app.js usam."""
    payload = to_report_payload(_report())
    assert payload["installedCount"] == 5
    assert len(payload["candidates"]) == 2
    folder = next(c for c in payload["candidates"] if c["kind"] == "folder")
    # chaves camelCase exigidas pela interface
    for key in ("sizeBytes", "sizeHuman", "ageDays", "manualCommand",
                "confidence", "sensitive", "evidences"):
        assert key in folder
    assert folder["evidences"][0] == {
        "description": "+40 ausente", "weight": 40, "source": "filesystem"}


def test_bridge_payload_is_json_serializable():
    import json

    json.dumps(to_report_payload(_report()), ensure_ascii=False)


def test_payload_includes_summary_plain():
    """A GUI exige uma frase-motivo legivel por candidato (spec 2026-09-21)."""
    payload = to_report_payload(_report())
    for cand in payload["candidates"]:
        assert cand["summaryPlain"]


def test_cli_json_gains_summary_plain_adotivo(tmp_path):
    """Contrato Orbit: snake_case preservado, campo novo apenas aditivo."""
    out = write_json(_report(), tmp_path / "rel.json")
    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    cand = data["candidates"][0]
    assert "summary_plain" in cand and cand["summary_plain"]
    assert "size_bytes" in cand  # nao removeu nada do shape antigo
