"""Report: arvore textual, filtro de confianca e export JSON."""

from vector.models import Evidence, OrphanCandidate, ScanReport
from vector.report import render_tree, write_json


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
