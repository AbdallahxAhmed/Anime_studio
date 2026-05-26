# Implementation Plan: TUI Dashboard

**Branch**: `005-tui-dashboard` | **Date**: 2026-05-26 | **Spec**: [spec.md](file:///d:/Dev/projects/Anime_studio/specs/005-tui-dashboard/spec.md)

**Input**: Feature specification from `specs/005-tui-dashboard/spec.md`

## Summary

Build the Textual 1.x TUI presentation layer for Anime Studio v3. The TUI is a pure consumer of `PipelineRunner` — it performs zero direct I/O. Features: dashboard screen with library path input and dry-run toggle, real-time activity feed derived from structlog INFO+ events via a custom message bridge, progress indicators (spinner for library scan, determinate bar for mux jobs), results summary panel, and styled error presentation. All background work uses Textual's `run_worker()`.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: textual 1.x (TUI framework), structlog (log bridge), pydantic v2 (models — consumed read-only)

**Storage**: None — TUI layer performs zero filesystem I/O

**Testing**: pytest + pytest-asyncio + Textual Pilot API

**Target Platform**: Windows-first (Windows Terminal / PowerShell 7+), cross-platform compatible

**Project Type**: TUI application (presentation layer of existing service)

**Performance Goals**: Dashboard renders in <2s, activity feed <500ms latency, progress bar <1s lag

**Constraints**: Zero direct I/O in TUI. Textual CSS only. Max ~10 UI updates/second for activity feed throttling.

**Scale/Scope**: Single dashboard screen, 1 pipeline run at a time, up to 50 episode progress items

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Hexagonal Architecture | ✅ PASS | TUI in `src/tui/`, consumes PipelineRunner via DI. No adapter/hunter imports. Bootstrap in composition root. |
| II. Cross-Platform | ✅ PASS | Textual handles terminal capability detection. No ANSI escape codes. `pathlib.Path` for all paths. |
| III. Async-First I/O | ✅ PASS | TUI uses `run_worker()` for background pipeline. No blocking calls. Single asyncio event loop. |
| IV. Structured Errors | ✅ PASS | All errors caught at worker boundary → Textual Notify/Modal. Never raw tracebacks. |
| V. Plugin Registry | ✅ N/A | TUI does not interact with hunter registry. |
| VI. Data Safety | ✅ N/A | TUI does not manipulate files. PipelineRunner handles data safety. |
| VII. Subprocess Lifecycle | ✅ N/A | TUI does not invoke subprocesses. |
| VIII. Encoding Guarantees | ✅ N/A | TUI does not handle encoding. |
| IX. Observability | ✅ PASS | TUI surfaces curated activity feed from INFO+ events. No raw log lines displayed. |
| X-bis. Report Generation | ✅ N/A | Report generation is PipelineRunner's responsibility. TUI displays report path. |
| X. Test-First | ✅ PASS | Textual Pilot API for widget tests. Boundary compliance test. |
| XII. YAGNI | ✅ PASS | No premature abstractions. One screen, minimal widget set. |
| XIII. Distribution | ✅ PASS | Entry point via `python -m src`. No new binaries needed. |

All gates pass. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/005-tui-dashboard/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── tui_contract.md  # TUI ↔ PipelineRunner interface contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── __main__.py              # [MODIFY] Entry point → launch TUI
├── tui/                     # [NEW] Entire TUI package
│   ├── __init__.py          # [NEW] Package init
│   ├── app.py               # [NEW] AnimeStudioApp(App) — main Textual app
│   ├── bootstrap.py         # [NEW] Composition root — wire adapters → PipelineRunner → App
│   ├── messages.py          # [NEW] Textual Message subclasses (LogEntry, ProgressUpdate, etc.)
│   ├── log_bridge.py        # [NEW] structlog processor → Textual message bridge
│   ├── screens/
│   │   ├── __init__.py      # [NEW]
│   │   └── dashboard.py     # [NEW] DashboardScreen — main screen
│   ├── widgets/
│   │   ├── __init__.py      # [NEW]
│   │   ├── activity_feed.py # [NEW] ActivityFeed widget (Log-based, throttled)
│   │   ├── progress_panel.py# [NEW] ProgressPanel (spinner + progress bar)
│   │   ├── results_summary.py# [NEW] ResultsSummary (post-pipeline)
│   │   └── error_modal.py   # [NEW] ErrorModal (ModalScreen for critical errors)
│   └── styles/
│       └── dashboard.tcss   # [NEW] Textual CSS for dashboard layout

tests/
├── unit/
│   └── tui/
│       ├── __init__.py       # [NEW]
│       ├── test_app.py       # [NEW] App lifecycle tests
│       ├── test_messages.py  # [NEW] Message construction tests
│       ├── test_log_bridge.py# [NEW] structlog bridge tests
│       ├── test_activity_feed.py # [NEW] Activity feed widget tests
│       ├── test_progress_panel.py# [NEW] Progress panel tests
│       ├── test_results_summary.py# [NEW] Results summary tests
│       └── test_boundary.py  # [NEW] Import boundary compliance test
```

**Structure Decision**: New `src/tui/` package following constitution's prescribed layout. Screens, widgets, and styles subdirectories. Bootstrap module serves as composition root. All new code — no modifications to existing source except `__main__.py`.

## Complexity Tracking

No violations. All patterns align with constitution.
