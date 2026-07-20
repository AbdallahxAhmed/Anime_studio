# Quickstart: Pipeline Control & Safety (Phase 7.5)

## What This Feature Does

Adds three safety capabilities to the Anime Studio pipeline:

1. **Smart Stop + Checkpoint**: Gracefully stop a running pipeline, save progress, resume later.
2. **Multi-level Undo**: Reverse pipeline operations (restore original files from trash) at episode, show, or full-run granularity.
3. **Test Fixes**: Fix 4 existing test failures.

## How to Use

### Stop a Running Pipeline

1. Click **Run Pipeline** / **Run Selected** as normal.
2. While the pipeline is running, a **Stop** button appears next to the Run button.
3. Click **Stop** — the current episode finishes processing, then the pipeline stops.
4. A checkpoint file is saved at `{library}/.anime_studio/pipeline_checkpoint.toml`.

### Resume a Stopped Pipeline

1. Select the same library path.
2. Click **Run Pipeline**.
3. A dialog appears: **Resume (skip N completed)** / **Start Fresh** / **Cancel**.
4. Choose Resume to continue where you left off.

### Undo Pipeline Operations

1. Click the **Undo** button in the toolbar.
2. Select a previous run from the dropdown (last 10 runs shown).
3. Choose undo level:
   - **Undo entire run** — restore all files
   - **Undo by show** — select which shows to restore
   - **Undo specific episodes** — select individual episodes
4. Click **OK** — original files are restored from `.anime_studio_trash/`.

## Technical Details

- Stop signal uses `asyncio.Event` (cooperative, never hard-kill)
- Checkpoint and manifest files are TOML (consistent with `config.toml`)
- Undo leverages existing trash system (30-day retention)
- All new services in `src/core/` (no GUI imports)
- `stop_event` passed as parameter to `PipelineRunner.run()`, NOT in `PipelineConfig`

## Run Tests

```bash
# All tests
uv run pytest tests/unit/ -v

# Just Phase 7.5 tests
uv run pytest tests/unit/models/test_run_manifest.py tests/unit/core/test_checkpoint_manager.py tests/unit/core/test_undo_service.py tests/unit/gui/test_undo_dialog.py -v
```
