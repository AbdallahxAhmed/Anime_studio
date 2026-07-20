# Quickstart: Pre-Packaging UX (Phase 7)

**Date**: 2026-06-06

## Overview

This feature adds three pre-packaging UX improvements:

1. **Selective Run** — Tree view with checkboxes to pick which shows/seasons to process
2. **Export Log** — One-click export of session logs to a text file
3. **Scanner Bug Fix** — Filter out `_amux_*.tmp.*` temp files from scan results

## Getting Started

### Prerequisites

- Python 3.11+
- All existing dependencies installed (`uv sync`)
- 231 existing tests passing (`uv run pytest tests/unit/`)

### Implementation Order

Follow the wave-based execution order in [plan.md](file:///d:/Dev/projects/Anime_studio/specs/009-pre-packaging-ux/plan.md):

1. **Wave 0**: Scanner temp file filter (T-C01, T-C02) — 5 min
2. **Wave 1**: New models ShowNode/SubFolderNode (T-A01, T-A02, T-A13) — 15 min
3. **Wave 2**: Scanner tree building + Log bridge buffer (parallel) — 30 min
4. **Wave 3**: PipelineRunner filtering + Export function (parallel) — 20 min
5. **Wave 4**: SelectionTreeWidget (T-A06 through T-A16) — 45 min
6. **Wave 5**: Export Log UI (T-B04, T-B05) — 15 min
7. **Wave 6**: MainWindow integration (T-A11, T-A12) — 30 min

### Key Files to Touch

| File | Change Type |
|------|-------------|
| `src/models/pipeline.py` | Add ShowNode, SubFolderNode, modify LibraryScanOutput + PipelineConfig |
| `src/core/library_scanner.py` | Build show_tree, add _amux_ filter |
| `src/core/pipeline_runner.py` | Filter by selected_paths |
| `src/gui/log_bridge.py` | Session buffer + format/export helpers |
| `src/gui/widgets/selection_tree.py` | NEW — SelectionTreeWidget |
| `src/gui/widgets/activity_feed.py` | Add Export Log button |
| `src/gui/main_window.py` | Two-phase run flow + export wiring |
| `src/gui/widgets/__init__.py` | Export SelectionTreeWidget |

### Running Tests

```bash
# After each wave, verify no regressions:
uv run pytest tests/unit/ -v

# Run only new tests:
uv run pytest tests/unit/ -v -k "ShowNode or SubFolderNode or show_tree or amux or selected_paths or selection_tree or log_export"
```

### Manual Testing

```bash
# Launch the GUI
uv run python -m src

# Test flow:
# 1. Pick anime library folder
# 2. Click "Run Pipeline" → tree view appears
# 3. Uncheck some shows/seasons
# 4. Click "Run Pipeline" again → only selected folders processed
# 5. Click "Export Log" → save file → verify contents
```

## Key Design Decisions

- **`frozenset` for selected_paths**: PipelineConfig is frozen Pydantic model → mutable `set` not allowed
- **`ItemIsAutoTristate`**: Qt built-in tri-state — zero custom propagation code
- **Log buffer in GuiLogBridge**: cleanest data source (structured dicts, not HTML)
- **State machine run flow**: single "Run Pipeline" button with `_awaiting_selection` flag
