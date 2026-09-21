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


# Frases em linguagem simples para a GUI (campo summaryPlain). Casadas por
# substring com a descricao da evidencia de maior peso: a fonte de verdade
# dos textos tecnicos continua nos scanners; aqui so a "traducao".
_PLAIN_PHRASES: tuple[tuple[str, str], ...] = (
    ("nome ausente nos programas instalados",
     "não aparece na lista de programas instalados do Windows, "
     "mas ainda há pastas dele no sistema"),
    ("chave sem programa correspondente",
     "chave de registro sem programa correspondente — a remoção é manual"),
    ("InstallLocation inexistente",
     "o registro aponta para uma pasta que não existe mais — a remoção é manual"),
    ("Run aponta",
     "iniciava com o Windows, mas o programa apontado não existe mais "
     "— a remoção é manual"),
    ("App Path quebrado",
     "atalho de execução do Windows quebrado — a remoção é manual"),
    ("servico aponta",
     "serviço aponta para um executável que não existe mais — a remoção é manual"),
    ("servico sem programa",
     "serviço sem programa correspondente instalado — a remoção é manual"),
    ("tarefa executa binario",
     "tarefa agendada aponta para um executável que não existe mais "
     "— a remoção é manual"),
    ("tarefa sem programa",
     "tarefa agendada sem programa correspondente — a remoção é manual"),
    ("resta ", "só tem resto de instalador/desinstalador para trás"),
    ("pasta abandonada", "está sem uso há muito tempo"),
    ("pasta vazia", "está vazia ou ilegível"),
)

_FALLBACK_FOLDER = "possível resíduo de programa desinstalado"
_FALLBACK_OTHER = "remoção manual recomendada"


def plain_summary(candidate: OrphanCandidate) -> str:
    """Uma frase-motivo, derivada da evidencia de maior peso. Nunca levanta excecao."""
    for ev in sorted(candidate.evidences, key=lambda e: e.weight, reverse=True):
        for needle, phrase in _PLAIN_PHRASES:
            if needle in ev.description:
                return phrase
    return _FALLBACK_FOLDER if candidate.kind == "folder" else _FALLBACK_OTHER
