# Data Model: TUI Dashboard

**Feature**: 005-tui-dashboard | **Date**: 2026-05-26

## TUI-Layer Models (Messages)

These are Textual `Message` subclasses used for internal TUI communication. They live in `src/tui/messages.py` — NOT in `src/models/` (they are presentation-layer types).

### LogEntry

Represents a single curated log event for the activity feed.

| Field | Type | Description |
|-------|------|-------------|
| timestamp | `datetime` | When event occurred |
| level | `str` | Log level: "info", "warning", "error" |
| event | `str` | Human-readable event description |
| context | `dict[str, Any]` | Structured context fields from structlog |

### ProgressUpdate

Represents a progress update for long-running operations.

| Field | Type | Description |
|-------|------|-------------|
| stage | `str` | Pipeline stage: "scan", "analysis", "mux", "done" |
| current | `int \| None` | Current item index (None = indeterminate) |
| total | `int \| None` | Total items (None = indeterminate) |
| label | `str` | Human-readable progress label |

### PipelineStarted / PipelineCompleted

Lifecycle messages posted by the pipeline worker.

**PipelineStarted**: No fields — signals transition to execution view.

**PipelineCompleted**:

| Field | Type | Description |
|-------|------|-------------|
| report | `PipelineReport` | Final report from PipelineRunner |
| success | `bool` | Whether pipeline completed without critical errors |

### PipelineError

| Field | Type | Description |
|-------|------|-------------|
| error | `AnimeStudioError` | Domain exception that occurred |
| fatal | `bool` | Whether pipeline must halt |

## Domain Models Consumed (from `src/models/`)

The TUI imports these read-only for display — zero mutations:

- `PipelineConfig` — constructed from UI inputs, passed to PipelineRunner
- `PipelineReport` — received from PipelineRunner.run() result
- `EpisodeReport` — iterated for results summary
- `EpisodeStatus` — enum for status icons (✓/⚠/✗)

## No New Domain Models

TUI does NOT add models to `src/models/`. All TUI-specific types stay in `src/tui/`.
