# Design

<!-- impeccable:design-schema 1 -->

## World

Dark surgical console: a near-black magenta-tinted field carrying a
single signature gradient (rosa plasma → magenta cirúrgico), monospace
technical labels, evidence cards with hairline borders. Mode:
**Operate** — the visitor is completing a real task (reviewing
evidence, confirming removals one by one), not being persuaded. The
gradient is spent once per screen (headline word, primary button,
active nav indicator, confidence HIGH badge), never as ambient
decoration.

Runs inside a WebView2 control hosted by a native, borderless Windows
form (`gui/VectorHost.ps1`) — Chromium rendering, but no browser
chrome, so the page owns its own custom titlebar and window controls.
Same shell pattern as Genesis, re-skinned in Vector magenta.

## Palette

| Token | Value | Use |
|---|---|---|
| `--bg` | `#14060f` | Base field (magenta-tinted near-black) |
| `--bg-elevated` | `#1e0a18` | Panels/cards |
| `--bg-elevated-2` | `#2a0f22` | Hover/active surface |
| `--bg-inset` | `#0d040b` | Inputs, log panel |
| `--border` / `--border-strong` | `rgba(249,168,212,.14 / .28)` | Hairlines |
| `--text` | `#fdf2f8` | Primary text |
| `--text-dim` | `#e8b4cd` | Secondary (tinted, ≥4.5:1 on bg) |
| `--text-faint` | `#9c6b85` | Tertiary/meta (mono ids, counters) |
| `--accent` / `--accent-deep` | `#F9A8D4` / `#DB2777` | The one signature gradient |
| `--primary` | `#EC4899` | Brand primary (badges, focus) |
| `--teal` | `#2dd9b9` | Success / removed state |
| `--amber` | `#fbbf5b` | Warning / sensitive-data alert |
| `--danger` | `#f8717a` | Fail / destructive confirm |
| `--high` / `--medium` / `--low` | `#F9A8D4` / `#fbbf5b` / `#93a1c4` | Confidence badges |

Color strategy: **Committed** — the dark field carries the whole
surface. Justified because the world is pinned evidence (PRODUCT.md
brand + Genesis-tested console pattern), not an invented aesthetic.

## Type

- Display/headings: `Segoe UI Variable Display` → `Segoe UI Semibold`
  → `Segoe UI` (native Windows 11 display face, ships with the OS).
- Body: `Segoe UI Variable Text` → `Segoe UI`.
- Technical (paths, weights, ids, log): `Cascadia Code` →
  `Cascadia Mono` → `Consolas`.

No web fonts, no downloads — portable offline artifact.

## Components

- **Titlebar** (`.titlebar`): custom chrome, draggable; magenta glyph
  mark + `VECTOR.EXE` mono wordmark; min/close buttons.
- **Sidebar nav** (`.side-*`): grouped steps (início, varredura,
  evidências, limpeza, concluído); 2px magenta inset border marks the
  current step, teal dot marks completed. Never a numbered stepper.
- **Evidence cards** (`.ev-card`): confidence badge (HIGH magenta
  fill / MEDIUM amber outline / LOW dim), path in mono, size/age meta,
  per-evidence weight rows, sensitive-data alert strip (amber),
  manual-command block for registry/service/task items. No
  same-size icon+heading+text card grids; the tree is a dense list.
- **Clean queue** (`.clean-*`): one candidate at a time, literal
  `REMOVER <n>` transcribe input + `s/N` confirm, explicit
  sensitive alert, skip-by-default. Navigation itself is the guard.
- **Progress/log** (`.log-panel`): mono feed of removed/skipped +
  summary counts + log path, backed later by the same event stream
  the console prints.

## Motion

One authored moment: the confidence badge pulse on scan-complete +
the clean-item slide transition (~140ms, exponential ease-out). No
entrance animations, no scroll reveals — task surface, feedback only.

## Provenance

Glyph is an authored inline SVG (crosshair + scalpel slash in Vector
magenta, `gui/vector/assets/vector-mark.svg`); the `.ico` is generated
from it by `scripts/make-exe-icon.ps1`. No external imagery, no stock,
no AI generation standing in for product truth. Mock evidence data in
`gui/vector/mock.js` mirrors `ScanReport`/`OrphanCandidate` shapes.

## Finish

Phase 2 wired: `app.js` now drives the real engine through the WebView2
`postMessage` bridge (`start-scan`/`remove-folder` → `scan-result`/
`remove-result`), with `mock.js` kept only as the fallback when the page is
opened directly in a browser or Python is missing. Verified here: the Python
bridge (`vector-cli.py --serve`) end-to-end, the camelCase payload shape
matching `mock.js`, the in-memory removal guard, and `node --check` on the
JS. NOT verified (needs a real Windows run): the live WebView2 hosting inside
the compiled `Vector.exe` — window drag, the persistent Python child process
under UAC elevation, and the scan/clean round-trip on screen. Treat the first
real run on the target machine as the finish review.
