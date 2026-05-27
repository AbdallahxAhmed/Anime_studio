# Implementation Plan: GUI Dashboard

**Branch**: `006-gui-dashboard` | **Date**: 2026-05-26 | **Spec**: [spec.md](file:///d:/Dev/projects/Anime_studio/specs/005-gui-dashboard/spec.md)

**Input**: Feature specification from `specs/005-gui-dashboard/spec.md`

## Summary

Build the Flet GUI presentation layer for Anime Studio v3, replacing the retired Textual TUI. The GUI is a pure consumer of `PipelineRunner` — it performs zero direct I/O. Features: Material Design dashboard with directory picker (`FilePicker`) and dry-run toggle, real-time activity feed derived from structlog INFO+ events via a custom log bridge processor, async progress indicators (ProgressRing for library scan, ProgressBar for mux jobs), sortable results DataTable, and styled error presentation (SnackBar + AlertDialog). All background work uses `page.run_task()` / `asyncio.create_task()` within Flet's single async event loop.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: flet (GUI framework — Material Design, async-native), structlog (log bridge), pydantic v2 (models — consumed read-only)

**Storage**: None — GUI layer performs zero filesystem I/O

**Testing**: pytest + pytest-asyncio

**Target Platform**: Windows-first, cross-platform compatible

**Project Type**: GUI application (presentation layer of existing service)

**Performance Goals**: Dashboard renders in <2s, activity feed <500ms latency, progress bar <1s lag, interaction response <200ms

**Constraints**: Zero direct I/O in GUI. Material Design visual language. Max ~10 UI updates/second for activity feed throttling. Single pipeline run at a time.

**Scale/Scope**: Single dashboard, 1 pipeline run at a time, up to 50 episodes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Hexagonal Architecture | ✅ PASS | GUI in `src/gui/`, consumes PipelineRunner via DI. No adapter/hunter/core imports except via bootstrap composition root. Zero business logic in presentation. |
| II | Cross-Platform | ✅ PASS | Flet renders its own window (Flutter engine) — no terminal capability concerns. `pathlib.Path` for any path display. No ANSI codes. |
| III | Async-First I/O | ✅ PASS | GUI uses `page.run_task()` / `asyncio.create_task()` for background pipeline. No blocking calls. Single asyncio event loop. Flet is async-native. |
| IV | Structured Errors | ✅ PASS | All errors caught at boundary → Flet `SnackBar` (non-critical) / `AlertDialog` (critical). Never raw tracebacks. |
| V | Plugin Registry | ✅ N/A | GUI does not interact with hunter registry directly. |
| VI | Data Safety | ✅ N/A | GUI does not manipulate files. PipelineRunner handles data safety. |
| VII | Subprocess Lifecycle | ✅ N/A | GUI does not invoke subprocesses. |
| VIII | Encoding Guarantees | ✅ N/A | GUI does not handle encoding. |
| IX | Observability | ✅ PASS | GUI surfaces curated activity feed from INFO+ events via structlog processor bridge. No raw log lines displayed. Progress events rendered as ProgressBar/ProgressRing. |
| X-bis | Report Generation | ✅ N/A | Report generation is PipelineRunner's responsibility. GUI displays report path in results table. |
| X | Test-First | ✅ PASS | Unit tests for messages, log bridge, and boundary compliance. Widget tests where Flet testing allows. |
| XI | Dependency Isolation | ✅ PASS | `flet` added to approved deps (replaces `textual`). No new unapproved dependencies. |
| XII | YAGNI | ✅ PASS | No premature abstractions. One screen, minimal widget set. No multi-screen navigation. |
| XIII | Distribution | ✅ PASS | Entry point via `python -m src`. No new binaries needed. Flet installed via `uv`/`pip`. |

All gates pass. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/005-gui-dashboard/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── gui_contract.md  # GUI ↔ PipelineRunner interface contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── __main__.py              # [MODIFY] Entry point → launch Flet app
├── gui/                     # [NEW] Entire GUI package
│   ├── __init__.py          # [NEW] Package init
│   ├── app.py               # [NEW] main(page) — Flet app entry
│   ├── bootstrap.py         # [NEW] Composition root — wire adapters → PipelineRunner → App
│   ├── messages.py          # [NEW] Message/event dataclasses for GUI updates
│   ├── log_bridge.py        # [NEW] structlog processor → GUI message bridge
│   ├── screens/
│   │   ├── __init__.py      # [NEW]
│   │   └── dashboard.py     # [NEW] DashboardView — main screen
│   ├── widgets/
│   │   ├── __init__.py      # [NEW]
│   │   ├── activity_feed.py # [NEW] ActivityFeed (Log-based, throttled ListView)
│   │   ├── progress_panel.py# [NEW] ProgressPanel (ProgressRing + ProgressBar)
│   │   ├── results_table.py # [NEW] ResultsTable (DataTable for post-run)
│   │   └── error_dialog.py  # [NEW] Error presentation (AlertDialog/SnackBar)
│   └── styles/
│       └── theme.py         # [NEW] Material Design theme config

tests/
├── unit/
│   └── gui/
│       ├── __init__.py       # [NEW]
│       ├── test_app.py       # [NEW] App lifecycle tests
│       ├── test_messages.py  # [NEW] Message construction tests
│       ├── test_log_bridge.py# [NEW] structlog bridge tests
│       ├── test_activity_feed.py # [NEW] Activity feed widget tests
│       ├── test_progress_panel.py# [NEW] Progress panel tests
│       ├── test_results_table.py # [NEW] Results table tests
│       └── test_boundary.py  # [NEW] Import boundary compliance test
```

**Structure Decision**: New `src/gui/` package replacing retired `src/tui/`, following constitution v1.6.0's prescribed layout. Screens, widgets, and styles subdirectories. Bootstrap module serves as composition root. Python-based styling (no TCSS — Flet uses Material Design theming). All new code — no modifications to existing source except `__main__.py`.

## Complexity Tracking

No violations. All patterns align with constitution v1.6.0.
