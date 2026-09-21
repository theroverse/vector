"""Pontuacao de evidencias -> nivel de confianca (HIGH / MEDIUM / LOW).

A regra e soma simples de pesos transparentes: cada Evidence carrega seu
peso e o relatorio pode exibi-los com `-v`. Allowlist zera qualquer
candidato via peso negativo alto.
"""

from __future__ import annotations

from vector.models import OrphanCandidate
from vector.settings import THRESHOLD_HIGH, THRESHOLD_MEDIUM
from vector.utils import is_allowlisted, looks_sensitive


def score_candidate(candidate: OrphanCandidate) -> OrphanCandidate:
    """Soma os pesos, marca sensitive e define confidence. Idempotente."""
    total = sum(ev.weight for ev in candidate.evidences)

    if is_allowlisted(candidate.label, candidate.path):
        total += -100  # WEIGHT_ALLOWLISTED: protege sistema/drivers

    candidate.score = total
    if total >= THRESHOLD_HIGH:
        candidate.confidence = "HIGH"
    elif total >= THRESHOLD_MEDIUM:
        candidate.confidence = "MEDIUM"
    else:
        candidate.confidence = "LOW"

    if looks_sensitive(candidate.path, candidate.label):
        candidate.sensitive = True

    return candidate


def score_all(candidates: list[OrphanCandidate]) -> list[OrphanCandidate]:
    """Pontua uma lista inteira e a devolve ordenada (score desc)."""
    scored = [score_candidate(c) for c in candidates]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored
