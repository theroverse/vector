"""Relatorio textual: arvore visual de evidencias no terminal + JSON."""

from __future__ import annotations

import json
from pathlib import Path

from vector.models import OrphanCandidate, ScanReport

_KIND_ICON = {
    "folder": "DIR",
    "registry": "REG",
    "service": "SVC",
    "task": "TASK",
}


def format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "tamanho n/d"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _detail(candidate: OrphanCandidate) -> str:
    parts = []
    if candidate.kind == "folder":
        parts.append(format_size(candidate.size_bytes))
        if candidate.age_days is not None:
            parts.append(f"{candidate.age_days} dias parado")
    else:
        parts.append(candidate.kind)
    if candidate.sensitive:
        parts.append("POSSIVEL DADO SENSIVEL")
    return ", ".join(parts)


def render_tree(report: ScanReport, min_confidence: str = "LOW",
                verbose: bool = False) -> str:
    """Monta a arvore ASCII. Nunca levanta excecao por candidato ruim."""
    order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    threshold = order.get(min_confidence.upper(), 1)
    items = [c for c in report.candidates
             if order.get(c.confidence, 0) >= threshold]

    title_target = f" (alvo: '{report.target}')" if report.target else ""
    lines = [
        f"Vector — relatorio de orfaos{title_target}",
        f"Programas instalados: {report.installed_count} | "
        f"candidatos: {len(items)}",
        "",
    ]
    if not items:
        lines.append("Nenhum residuo encontrado para os criterios atuais. :)")
        lines.append("Dica: rode sem --target para varrer tudo, ou use -v.")
    for candidate in items:
        icon = _KIND_ICON.get(candidate.kind, "?")
        lines.append(
            f"+-- [{candidate.confidence} {candidate.score:>3}] "
            f"[{icon}] {candidate.path} ({_detail(candidate)})"
        )
        for evidence in candidate.evidences:
            if verbose:
                lines.append(f"    |-- ({evidence.source}) {evidence.description}")
            else:
                lines.append(f"    |-- {evidence.description}")
        if candidate.manual_command:
            lines.append(f"    +-- manual: {candidate.manual_command}")
        elif candidate.evidences:
            # Marca o fim do bloco quando nao ha comando manual.
            lines[-1] = lines[-1].replace("    |--", "    +--", 1) \
                if len(candidate.evidences) == 1 else lines[-1]
    if report.access_denied:
        lines.append("")
        lines.append("[!] Sem permissao em "
                     f"{len(report.access_denied)} caminho(s) "
                     "(rode como admin p/ cobertura total):")
        for denied in report.access_denied[:10]:
            lines.append(f"    - {denied}")
        if len(report.access_denied) > 10:
            lines.append(f"    ... e mais {len(report.access_denied) - 10}.")
    if report.warnings:
        lines.append("")
        for warning in report.warnings:
            lines.append(f"[aviso] {warning}")
    return "\n".join(lines)


def write_json(report: ScanReport, destination: Path) -> Path:
    """Exporta o relatorio em JSON (para Orbit/automacoes)."""
    payload = {
        "target": report.target,
        "installed_count": report.installed_count,
        "roots_scanned": report.roots_scanned,
        "access_denied": report.access_denied,
        "warnings": report.warnings,
        "candidates": [
            {
                "kind": c.kind,
                "path": c.path,
                "label": c.label,
                "score": c.score,
                "confidence": c.confidence,
                "sensitive": c.sensitive,
                "size_bytes": c.size_bytes,
                "age_days": c.age_days,
                "manual_command": c.manual_command,
                "evidences": [
                    {"description": e.description, "weight": e.weight,
                     "source": e.source} for e in c.evidences
                ],
            }
            for c in report.candidates
        ],
    }
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    return destination


def to_report_payload(report: ScanReport) -> dict:
    """Serializa o relatorio na forma camelCase que a GUI (mock.js/app.js) ja
    espera. Adaptador na fronteira do bridge: o `--json` da CLI mantem o shape
    snake_case (contrato Orbit/automacao); aqui e a view da interface."""
    return {
        "target": report.target,
        "installedCount": report.installed_count,
        "rootsScanned": list(report.roots_scanned),
        "accessDenied": list(report.access_denied),
        "warnings": list(report.warnings),
        "candidates": [
            {
                "kind": c.kind,
                "path": c.path,
                "label": c.label,
                "score": c.score,
                "confidence": c.confidence,
                "sensitive": c.sensitive,
                "sizeBytes": c.size_bytes,
                "sizeHuman": format_size(c.size_bytes),
                "ageDays": c.age_days,
                "manualCommand": c.manual_command,
                "evidences": [
                    {"description": e.description, "weight": e.weight,
                     "source": e.source} for e in c.evidences
                ],
            }
            for c in report.candidates
        ],
    }
