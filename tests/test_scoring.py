"""Pontuacao: soma de pesos, thresholds e allowlist."""

from vector.models import Evidence, OrphanCandidate
from vector.scoring import score_all, score_candidate


def _cand(label, path, weights):
    return OrphanCandidate(
        kind="folder", path=path, label=label,
        evidences=[Evidence(description=f"e{i}", weight=w, source="t")
                   for i, w in enumerate(weights)],
    )


def test_high_threshold():
    c = score_candidate(_cand("OldApp", r"C:\x\OldApp", [40, 30]))
    assert (c.score, c.confidence) == (70, "HIGH")


def test_medium_threshold():
    c = score_candidate(_cand("OldApp", r"C:\x\OldApp", [40]))
    assert (c.score, c.confidence) == (40, "MEDIUM")


def test_low_below_threshold():
    c = score_candidate(_cand("OldApp", r"C:\x\OldApp", [10]))
    assert c.confidence == "LOW"


def test_allowlist_neutralizes_high_score():
    c = score_candidate(_cand("NVIDIA", r"C:\Program Files\NVIDIA", [40, 30, 20]))
    assert c.confidence == "LOW"
    assert c.score < 40


def test_sensitive_flagged():
    c = score_candidate(_cand("GameSave", r"C:\x\GameSave\save", [40]))
    assert c.sensitive is True
    assert c.confidence == "MEDIUM"  # score mantido, so marca


def test_score_all_sorts_desc():
    ranked = score_all([
        _cand("A", r"C:\x\A", [10]),
        _cand("B", r"C:\x\B", [40, 30]),
    ])
    assert [c.label for c in ranked] == ["B", "A"]
