# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated: vanilla HTML/CSS/JS, no framework, no build step. Reasoning:
the surface is hosted inside a WebView2 control embedded in a native
PowerShell/.NET shell (compiled to a single `Vector.exe` via ps2exe) —
there is no server and no bundler in this environment, and the whole
point is a portable folder of plain files sitting next to the exe. The
HTML/JS renders mock evidence data in this phase (option 1: visual
approval first); the real Python engine (`src/vector/engine.py`) is
wired through WebView2's `postMessage` bridge in a later phase
(option 4). Same architecture as `genesis/gui/wizard/` + `build.ps1`.

## Users

Single user (the machine's owner) doing surgical uninstall cleanup on
their own Windows 11 PC, running as Administrator. The job: scan for
leftover junk from uninstalled programs, review an evidence tree with
confidence levels, and remove only what they explicitly confirm —
never losing an important file by mistake.

## Product Purpose

Vector is the surgical-cleanup ship of the Theroverse ecosystem. It
exists so that uninstalling a program stops leaving gigabytes of
orphaned files, registry keys, services and scheduled tasks behind:
audit first (evidence tree with HIGH/MEDIUM/LOW confidence), delete
later — and never by scare. This phase builds the visual interface +
single-file EXE shell with mock data so the owner can approve the look
and flow before it touches the real system.


## Positioning

Not a commercial product — the meaningful difference is against the
project's own current state (a text-only Python CLI printing an ASCII
tree in the console): this surface gives the same audit-then-clean
ritual a real, polished, guided flow without adding any backend,
telemetry, or hosted component. Everything still runs 100% local and
offline. The CLI (`vector-cli.py --scan/--clean`) remains the engine
and the source of truth for scoring rules.

## Operating Context

- Runs on the owner's own Windows 11 PC, as Administrator (UAC
  elevation), alongside the real programs it audits.
- The real system changes are performed by `src/vector/*.py` — this
  phase's UI renders representative mock data with identical shape;
  the bridge wiring comes later and must not change scoring rules.
- Must keep working as a single portable artifact: `Vector.exe` plus
  its sibling folders (`src/`, `gui/`) — no Node/npm to build.
- Interface language is Portuguese (pt-BR), matching the CLI strings.

## Capabilities and Constraints

- WebView2 Runtime ships built into Windows 11; if missing, the shell
  must explain plainly instead of crashing silently.
- Screens: welcome, scan setup (target/confidence/verbose), evidence
  tree (grouped by confidence, weights, size/age, sensitive flags,
  manual commands), interactive clean (REMOVER <n> + s/N, LOW never
  offered), done/log.
- Safety rules are product truth: LOW never offered, allowlist never
  suggested, registry/services/tasks never auto-removed,
  PermissionError reported with the "run as admin" hint.
- Brand color (distinct from siblings in ecosystem.ts): Vector
  Magenta — primary `#EC4899`, secondary `#DB2777`, accent
  `#F9A8D4`, glow `rgba(236, 72, 153, 0.45)`, dark `#14060f`.
  Siblings occupy cyan (Nexo), violet (Genesis), emerald (Athena),
  lime (Zeus), orange (Thero). Name: "Magenta Cirurgico & Rosa Plasma".
- No image-generation tool here. Glyph is authored inline SVG
  (crosshair/scalpel in Vector magenta); `.ico` generated from SVG
  via PowerShell (same approach as Genesis make-exe-icon.ps1).

## Evidence on Hand

- `src/vector/*.py` + `scanners/*.py` are the working source of truth
  for scanning, weights and safety — mock data mirrors the
  ScanReport/OrphanCandidate/Evidence shapes exactly.
- The CLI is the behavioral reference (flags, tree, confirmations),
  NOT a visual reference.
- Genesis (`gui/wizard/` + `WizardHost.ps1` + `build.ps1`) is the
  architectural reference for the WebView2 shell, ps2exe build and
  the postMessage protocol — port the pattern, not the styling.

## Product Principles

1. Front-end only: presents evidence, collects explicit per-item
   confirmation — never reimplements scanning/scoring.
2. Audit first, delete later: literal typed confirmation + second
   explicit yes; empty input always means skip.
3. Single portable offline artifact: no telemetry, no hosted assets.
4. Dangerous items (LOW, allowlist, auto-removal of registry) are
   structurally impossible in the clean flow, not just discouraged.

## Accessibility & Inclusion

Standard good practice (pink accent on near-black ≥ 4.5:1 for body,
keyboard focus order, readable type) — single named user's own tool.
