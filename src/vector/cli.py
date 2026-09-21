"""CLI do Vector: --scan (padrao, auditoria) e --clean (interativo)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HELP_EPILOG = r"""
MODOS
    --scan             Auditoria textual: varre e imprime a arvore de
                       evidencias. E o padrao (rodar sem flags = --scan).
                       Nunca apaga nada. Exit code sempre 0.
    --clean            Limpeza interativa: oferece cada pasta HIGH/MEDIUM
                       uma a uma, exigindo digitacao literal + confirmacao.
                       Registro/servicos/tarefas nunca sao removidos
                       sozinhos: o relatório mostra o comando manual.

FILTROS
    --target NOME      Investiga so um programa (ex.: --target Notion).
                       Compara de forma aproximada ("notion" casa com
                       "Notion 3.1").
    --min-confidence N Mostra so candidatos >= N (LOW, MEDIUM ou HIGH).
    --json ARQUIVO     Exporta o relatorio completo em JSON.
    -v, --verbose      Mostra a fonte de cada evidencia (scanner).

EXEMPLOS
    python vector.py
    python vector.py --scan --target Notion
    python vector.py --scan --min-confidence MEDIUM -v
    python vector.py --scan --json relatorio.json
    python vector.py --clean --target Notion

SEGURANCA
    LOW nunca e oferecido no --clean. Caminhos de sistema (Microsoft,
    Windows, drivers) estao na allowlist e nunca sao sugeridos. Pastas
    com possivel dado sensivel (save, backup, wallet, projeto, foto)
    disparam alerta explicito antes de qualquer confirmacao.
"""

_VALID_CONFIDENCES = ("LOW", "MEDIUM", "HIGH")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="vector.py",
        description="Nave Vector: desinstalacao avancada e rastreio de "
                    "residuos por evidencias.",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--scan", action="store_true",
                        help="Modo auditoria textual (padrao).")
    parser.add_argument("--clean", action="store_true",
                        help="Modo limpeza interativa com confirmacao.")
    parser.add_argument("--serve", action="store_true",
                        help=argparse.SUPPRESS)  # bridge JSON-lines p/ VectorHost.ps1
    parser.add_argument("--target", default=None, metavar="NOME",
                        help="Investiga so um programa (comparacao aproximada).")
    parser.add_argument("--min-confidence", default="LOW", metavar="NIVEL",
                        help="Filtra a arvore (LOW, MEDIUM ou HIGH).")
    parser.add_argument("--json", default=None, metavar="ARQUIVO",
                        help="Exporta o relatorio completo em JSON.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Mostra a fonte de cada evidencia.")
    return parser.parse_args(argv)


def main() -> None:
    from vector import engine
    from vector.cleaner import run_clean
    from vector.report import render_tree, write_json

    args = parse_args()

    if args.serve:
        # Modo servidor da GUI (fase 2): le pedidos JSON por stdin, responde
        # na stdout. Todo o guard de seguranca mora em vector.bridge.
        from vector.bridge import serve

        serve()
        return

    if args.scan and args.clean:
        print("[ERROR] Use --scan ou --clean, nunca os dois juntos.")
        sys.exit(2)

    min_conf = str(args.min_confidence).upper()
    if min_conf not in _VALID_CONFIDENCES:
        print(f"[ERROR] --min-confidence invalido: {args.min_confidence} "
              f"(use LOW, MEDIUM ou HIGH).")
        sys.exit(2)

    mode_clean = bool(args.clean)
    report = engine.run_scan(target=args.target)

    if args.json:
        try:
            saved = write_json(report, Path(args.json))
            print(f"[OK] Relatorio JSON salvo em: {saved}")
        except (PermissionError, OSError) as exc:
            print(f"[ERROR] Nao foi possivel salvar o JSON: {exc}")
            sys.exit(1)

    if mode_clean:
        sys.exit(run_clean(report))

    print(render_tree(report, min_confidence=min_conf, verbose=args.verbose))
