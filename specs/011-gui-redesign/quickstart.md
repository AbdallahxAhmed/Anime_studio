# Quickstart: GUI Redesign — Two-Panel Layout

**Phase 1 Output** | **Date**: 2026-06-27

## What Changed

The GUI layout switches from a vertical stack (all widgets crammed top-to-bottom)
to a two-panel layout:

- **Left sidebar** (220px): show list with status icons, "Add Folder" button
- **Right main panel**: episode table with checkboxes + status badges, collapsible activity log

The critical behavior change: the app NO LONGER scans the entire library on
startup. Instead it loads a cached show index instantly and only scans individual
folders on demand.

## Implementation Order

```
1. Add ShowStatus + ShowSummary to models/pipeline.py
2. Create ShowSidebarWidget + EpisodeTableWidget (new files)
3. Create ShowIndexManager in core/ + add scan_folder() to LibraryScanner
4. Make ActivityFeed collapsible, simplify ProgressPanel
5. Rewrite MainWindow layout + slots + bootstrap wiring
6. Delete selection_tree.py + library_picker.py
7. Verify: ruff + mypy + boundary test + full pytest suite
```

## Key Files

| Purpose | File |
|---------|------|
| Feature spec | `specs/011-gui-redesign/spec.md` |
| Implementation plan | `specs/011-gui-redesign/plan.md` |
| Research decisions | `specs/011-gui-redesign/research.md` |
| Data models | `specs/011-gui-redesign/data-model.md` |
| Constitution | `.specify/memory/constitution.md` (v1.7.0, unchanged) |

## Verification Commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/ --strict
uv run pytest tests/unit/ -v
uv run pytest tests/unit/gui/test_boundary.py -v
```

## Constitution Compliance

GUI widgets import ONLY `src.models.*` and `src.gui.signals`.
All async GUI methods use `@asyncSlot`.
All file I/O uses `asyncio.to_thread()`.
No `asyncio.Queue` — only `SignalBridge` signals.
`pathlib.Path` everywhere. `encoding="utf-8"` on all `open()`.
