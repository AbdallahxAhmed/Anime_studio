# Quickstart: TUI Dashboard

**Feature**: 005-tui-dashboard | **Date**: 2026-05-26

## Running the TUI

```bash
# From project root with venv activated
python -m src
```

This launches the Textual TUI dashboard.

## Development Mode

```bash
# Hot-reload during development
textual run --dev src/tui/app.py
```

## Testing

```bash
# Unit tests (Textual Pilot API)
pytest tests/unit/tui/ -v

# Verify hexagonal boundary compliance
pytest tests/unit/tui/test_boundary.py -v
```

## Smoke Test Scenarios

### Scenario 1: Dashboard Launch
1. Run `python -m src`
2. Verify dashboard renders with header, path input, dry-run toggle, and "Run Pipeline" button
3. Press `q` to quit

### Scenario 2: Pipeline Run (Dry-Run)
1. Launch app
2. Enter a valid library path containing MKV + ASS files
3. Enable "Dry Run" checkbox
4. Press "Run Pipeline"
5. Verify: spinner appears during scan, progress bar for mux, activity feed shows events
6. Verify: no files modified on disk
7. Verify: results summary shows per-episode status

### Scenario 3: Error Handling
1. Launch app
2. Enter a non-existent path
3. Press "Run Pipeline"
4. Verify: styled error notification appears (not a traceback)
