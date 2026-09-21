"""Modo --clean: limpeza interativa com confirmacao explicita item a item."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from vector.models import OrphanCandidate, ScanReport
from vector.report import format_size
from vector.settings import CLEAN_LOG_DIRNAME, CLEAN_LOG_FILENAME


def _log_line(message: str) -> Path:
    log_dir = Path.home() / CLEAN_LOG_DIRNAME
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / CLEAN_LOG_FILENAME
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")
        return log_path
    except (PermissionError, OSError):
        fallback = Path.cwd() / CLEAN_LOG_FILENAME
        with fallback.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")
        return fallback


def _confirm(prompt: str) -> bool:
    try:
        answer = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n[Vector] Entrada interrompida: pulando item.")
        return False
    return answer in ("s", "sim", "y", "yes")


def _remove_folder(path: str) -> tuple[bool, str]:
    target = Path(path)
    try:
        if target.is_file():
            target.unlink()
            return True, "arquivo removido"
        shutil.rmtree(target, onerror=_rmtree_onerror)
        return True, "pasta removida"
    except FileNotFoundError:
        return False, "item ja nao existe"
    except PermissionError:
        return False, "sem permissao (rode como admin)"
    except OSError as exc:
        return False, f"falha de E/S: {exc.strerror or exc}"


def _rmtree_onerror(func, path, exc_info):
    # shutil.rmtree chama isso por arquivo com problema; PermissionError
    # vira excecao propagada para _remove_folder relatar com elegancia.
    exc = exc_info[1] if exc_info else None
    if isinstance(exc, PermissionError):
        raise exc
    try:
        func(path)
    except (PermissionError, OSError) as retry_exc:
        raise retry_exc


def run_clean(report: ScanReport) -> int:
    """Loop interativo. Retorna exit code (0 = ok, 1 = nada feito/erro)."""
    items = report.cleanable
    print("=" * 70)
    print("Vector — MODO LIMPEZA (interativo, nada e apagado sem confirmar)")
    print("=" * 70)
    only_manual = [c for c in items if c.kind != "folder"]
    folders = [c for c in items if c.kind == "folder"]

    if only_manual:
        print("\n[!] Estes itens NAO sao removidos automaticamente. "
              "Execute o comando manual se desejar:")
        for candidate in only_manual:
            print(f"  - [{candidate.confidence}] {candidate.path}")
            if candidate.manual_command:
                print(f"      {candidate.manual_command}")
        _log_line(f"scan target={report.target} manual_items={len(only_manual)}")

    if not folders:
        print("\n[Vector] Nenhuma pasta HIGH/MEDIUM para remover. Nada feito.")
        return 0

    print(f"\n{len(folders)} pasta(s) elegiveis (HIGH/MEDIUM). "
          "LOW nunca e oferecido. Ctrl+C pula tudo com seguranca.\n")

    removed = skipped = 0
    for number, candidate in enumerate(folders, start=1):
        _show_candidate(number, candidate)
        expected = f"REMOVER {number}"
        try:
            typed = input(f'Digite "{expected}" para continuar (Enter pula): ').strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Vector] Interrompido pelo usuario. Encerrando sem remover.")
            _log_line(f"interrompido removed={removed} skipped={skipped}")
            break
        if typed != expected:
            print("  -> pulado.\n")
            skipped += 1
            _log_line(f"PULADO {candidate.path}")
            continue
        if not _confirm("Confirmar REMOCAO definitiva? [s/N]: "):
            print("  -> pulado (sem confirmacao).\n")
            skipped += 1
            _log_line(f"PULADO {candidate.path}")
            continue
        ok, detail = _remove_folder(candidate.path)
        print(f"  -> {'[OK]' if ok else '[FALHA]'} {detail}.\n")
        _log_line(f"{'REMOVIDO' if ok else 'FALHA'} {candidate.path} ({detail})")
        if ok:
            removed += 1
        else:
            skipped += 1

    print(f"[Vector] Limpeza concluida: {removed} removida(s), {skipped} pulada(s).")
    print(f"[Vector] Log em: {Path.home() / CLEAN_LOG_DIRNAME / CLEAN_LOG_FILENAME}")
    return 0


def _show_candidate(number: int, candidate: OrphanCandidate) -> None:
    print(f"--- [{number}] [{candidate.confidence} {candidate.score}] {candidate.path}")
    print(f"    ({format_size(candidate.size_bytes)})")
    for evidence in candidate.evidences:
        print(f"    - {evidence.description}")
    if candidate.sensitive:
        print("    [!] ALERTA: possivel DADO SENSIVEL neste caminho "
              "(save/backup/wallet/projeto/foto).")
        print("    [!] Remover pode causar PERDA IRREVERSIVEL. "
              "Confira o conteudo antes de confirmar.")
    sys.stdout.flush()
