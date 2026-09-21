"""Modelos de dados do Vector: evidencias, candidatos orfaos e relatorios."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Evidence:
    """Uma pista individual encontrada por um scanner.

    Attributes:
        description: Texto legivel exibido na arvore (ex.: "+40 nome ausente...").
        weight: Peso somado na pontuacao. Pode ser negativo (allowlist).
        source: Qual scanner gerou (ex.: "filesystem", "registry").
    """

    description: str
    weight: int
    source: str


@dataclass
class OrphanCandidate:
    """Um item suspeito de ser residuo de programa desinstalado."""

    kind: str  # "folder" | "registry" | "service" | "task"
    path: str  # caminho da pasta, chave de registro ou nome do servico/tarefa
    label: str  # nome curto exibido na arvore
    evidences: list[Evidence] = field(default_factory=list)
    size_bytes: int = 0
    age_days: int | None = None
    sensitive: bool = False
    # Comando manual sugerido para itens que o Vector NAO remove sozinho
    # (chaves de registro, servicos, tarefas agendadas).
    manual_command: str = ""
    score: int = 0
    confidence: str = "LOW"  # HIGH | MEDIUM | LOW


@dataclass
class ScanReport:
    """Resultado agregado de uma varredura completa."""

    target: str | None
    candidates: list[OrphanCandidate] = field(default_factory=list)
    installed_count: int = 0
    roots_scanned: list[str] = field(default_factory=list)
    access_denied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def cleanable(self) -> list[OrphanCandidate]:
        """Candidatos que podem ser oferecidos no --clean (HIGH/MEDIUM)."""
        from vector.settings import CLEANABLE_CONFIDENCES

        return [c for c in self.candidates if c.confidence in CLEANABLE_CONFIDENCES]
