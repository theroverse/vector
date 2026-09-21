"""Orquestrador: roda inventario + todos os scanners e pontua o resultado."""

from __future__ import annotations

from vector import inventory
from vector.models import ScanReport
from vector.scanners import filesystem, registry, services, tasks
from vector.scoring import score_all


def run_scan(target: str | None = None) -> ScanReport:
    """Executa a varredura cruzada completa e devolve o relatorio pontuado."""
    installed, inv_warnings = inventory.get_installed_programs()

    fs_result = filesystem.scan_filesystem(installed, target=target)
    reg_candidates, reg_warnings = registry.scan_registry(installed, target=target)
    svc_candidates, svc_warnings = services.scan_services(installed, target=target)
    task_candidates, task_warnings = tasks.scan_tasks(installed, target=target)

    all_candidates = (
        fs_result.candidates + reg_candidates + svc_candidates + task_candidates
    )
    scored = score_all(all_candidates)

    warnings = inv_warnings + reg_warnings + svc_warnings + task_warnings

    return ScanReport(
        target=target,
        candidates=scored,
        installed_count=len(installed),
        roots_scanned=fs_result.roots_scanned,
        access_denied=fs_result.access_denied,
        warnings=warnings,
    )
