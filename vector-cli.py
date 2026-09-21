#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

# Saida em ordem mesmo quando redirecionada (pipe/arquivo).
sys.stdout.reconfigure(line_buffering=True)

_ENTRY_PATH = Path(__file__).resolve()
_SRC_DIR = _ENTRY_PATH.parent / "src"

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from vector.cli import main

if __name__ == "__main__":
    main()
