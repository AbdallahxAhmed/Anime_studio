# Quickstart: GUI Dashboard

**Feature**: 005-gui-dashboard | **Date**: 2026-05-26

## Prerequisites

- Python 3.11+
- `uv` package manager (or `pip`)
- All CRITICAL tools installed: `ffmpeg`, `mkvmerge`, `mkvextract`
- An anime library directory with MKV + ASS files

## Install Dependencies

```powershell
# From repo root
uv pip install flet structlog pydantic

# Dev dependencies
uv pip install pytest pytest-asyncio ruff mypy
```

## Run the GUI

```powershell
# From repo root
python -m src
```

This launches the Flet GUI window. The dashboard displays:
1. A Material Design header
2. Directory picker button → opens native folder picker
3. "Dry Run" checkbox toggle
4. "Run Pipeline" button (disabled until a directory is selected)

## Typical Workflow

1. Click **Browse** → select anime library folder
2. Optionally toggle **Dry Run**
3. Click **Run Pipeline**
4. Watch:
   - Activity feed shows live log entries
   - Spinner while scanning library
   - Progress bar during muxing (N/M episodes)
5. When complete:
   - Results table shows per-episode status
   - Report path displayed

## Run Tests

```powershell
# Unit tests only
pytest tests/unit/gui/ -v

# Boundary compliance test (verifies import restrictions)
pytest tests/unit/gui/test_boundary.py -v

# All tests
pytest tests/ -v
```

## Key Files

| File | Purpose |
|------|---------|
| `src/gui/app.py` | Flet app entry point (`main(page)`) |
| `src/gui/bootstrap.py` | Composition root — wires adapters → pipeline → GUI |
| `src/gui/messages.py` | GUI message dataclasses |
| `src/gui/log_bridge.py` | structlog → asyncio.Queue bridge |
| `src/gui/screens/dashboard.py` | Main dashboard view |
| `src/gui/widgets/` | Activity feed, progress panel, results table, error dialog |
| `src/gui/styles/theme.py` | Material Design theme config |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "ToolNotFoundError" on launch | Install missing CRITICAL tools (`ffmpeg`, `mkvmerge`, `mkvextract`). See error dialog for install instructions. |
| GUI window doesn't appear | Ensure `flet` is installed: `uv pip install flet` |
| Blank activity feed | Check structlog is configured. The log bridge must be in the processor chain (handled by `bootstrap.py`). |
| Progress bar stuck | Check if mux jobs are completing. Look at log file in `~/.anime_studio/logs/`. |
