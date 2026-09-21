"""Pontuacao: soma de pesos, thresholds, allowlist e frase-motivo (plain)."""

from vector.models import Evidence, OrphanCandidate
from vector.scoring import plain_summary, score_all, score_candidate


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


# ---------------- plain_summary: frase-motivo para usuarios leigos ----------

def _pcand(kind, *descriptions):
    return OrphanCandidate(
        kind=kind, path=r"C:\Program Files\Foo", label="Foo",
        evidences=[Evidence(description=d, weight=w, source="t")
                   for w, d in descriptions],
    )


def test_plain_summary_uses_dominant_evidence():
    c = _pcand("folder",
               (10, "+10 pasta vazia ou ilegivel"),
               (40, "+40 nome ausente nos programas instalados"))
    assert "lista de programas instalados" in plain_summary(c)


def test_plain_summary_registry_manual():
    c = _pcand("registry", (40, "+40 chave sem programa correspondente instalado"))
    s = plain_summary(c)
    assert "registro" in s and "manual" in s


def test_plain_summary_leftover_uninstaller():
    c = _pcand("folder", (15, "+15 resta unins000.exe sem entrada de desinstalacao"))
    assert plain_summary(c) == "só tem resto de instalador/desinstalador para trás"


def test_plain_summary_fallbacks():
    empty = OrphanCandidate(kind="folder", path=r"C:\x", label="x", evidences=[])
    assert plain_summary(empty) == "possível resíduo de programa desinstalado"
    assert "manual" in plain_summary(
        _pcand("service", (7, "+7 evidencia que nao conheco")))
