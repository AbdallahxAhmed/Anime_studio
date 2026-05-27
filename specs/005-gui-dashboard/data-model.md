# Data Model: GUI Dashboard

**Feature**: 005-gui-dashboard | **Date**: 2026-05-26

## Overview

GUI-specific data types for message passing between the log bridge / pipeline callbacks and the Flet widgets. These are **presentation-layer types** — they live in `src/gui/messages.py` and have zero overlap with domain models in `src/models/`. They are plain dataclasses (not Pydantic) since they don't need validation or serialization.

## Entities

### ActivityEntry

Represents a single curated log entry for display in the activity feed.

```python
@dataclass(frozen=True, slots=True)
class ActivityEntry:
    timestamp: datetime          # When the event occurred
    level: str                   # "info", "warning", "error", "critical"
    category: str                # Event category (e.g., "scanner", "muxer", "font")
    message: str                 # Human-readable summary
    details: dict[str, Any] | None = None  # Optional structured context for tooltip/expansion
```

**Source**: Created by `GuiLogBridge` processor from structlog event dicts.
**Consumer**: `ActivityFeed` widget.
**Validation**: `level` must be one of the four accepted levels (enforced by bridge, not by dataclass).

---

### ProgressState

Represents the current state of pipeline progress for the progress panel.

```python
@dataclass(slots=True)
class ProgressState:
    phase: ProgressPhase         # Current pipeline phase
    completed: int = 0           # Episodes/items completed
    total: int = 0               # Total episodes/items (0 = indeterminate)
    label: str = ""              # Human-readable status text

class ProgressPhase(StrEnum):
    IDLE = "idle"
    SCANNING = "scanning"        # Indeterminate spinner
    MUXING = "muxing"            # Determinate progress bar
    COMPLETE = "complete"        # Final state — show summary
    ERROR = "error"              # Pipeline halted
```

**Source**: Emitted by pipeline callbacks during `PipelineRunner.run()`.
**Consumer**: `ProgressPanel` widget.
**State transitions**: `IDLE → SCANNING → MUXING → COMPLETE` (happy path), any phase → `ERROR` (failure).

---

### EpisodeResult

Represents a single row in the post-run results table.

```python
@dataclass(frozen=True, slots=True)
class EpisodeResult:
    name: str                    # Episode display name (e.g., "Episode 01 - Title")
    status: EpisodeStatus        # ✓ complete, ⚠ partial, ✗ failed
    fonts_found: int             # Number of fonts successfully resolved
    fonts_missing: int           # Number of genuine font misses
    error_summary: str | None = None  # Brief error description if failed/partial

class EpisodeStatus(StrEnum):
    COMPLETE = "complete"        # ✓
    PARTIAL = "partial"          # ⚠
    FAILED = "failed"            # ✗
```

**Source**: Mapped from `PipelineReport.episode_reports` after pipeline completion.
**Consumer**: `ResultsTable` widget.

---

### PipelineRunResult

Aggregate result passed to the dashboard after pipeline completion.

```python
@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    episodes: list[EpisodeResult]
    total_duration_seconds: float
    report_path: str             # Path to _AnimeStudio_Report.md (display only, no I/O)
    total_fonts_found: int
    total_fonts_missing: int
    dry_run: bool
```

**Source**: Mapped from `PipelineReport` by the bootstrap/bridge layer.
**Consumer**: `ResultsTable` widget + summary display.

---

### ErrorInfo

Structured error data for error dialog/notification presentation.

```python
@dataclass(frozen=True, slots=True)
class ErrorInfo:
    title: str                   # Short error title
    message: str                 # Human-readable error description
    suggestion: str | None = None  # Remediation hint
    is_critical: bool = False    # True → AlertDialog modal, False → SnackBar notification
```

**Source**: Caught exceptions at pipeline boundary, converted by bridge layer.
**Consumer**: `error_dialog.py` — chooses AlertDialog vs SnackBar based on `is_critical`.

---

## Relationships

```
PipelineRunner.run()
    │
    ├──(structlog events)──→ GuiLogBridge ──→ asyncio.Queue<ActivityEntry>
    │                                              │
    │                                              └──→ ActivityFeed widget
    │
    ├──(progress callbacks)──→ ProgressState ──→ ProgressPanel widget
    │
    ├──(completion)──→ PipelineReport
    │                       │
    │                       └──(mapping)──→ PipelineRunResult ──→ ResultsTable widget
    │
    └──(exceptions)──→ ErrorInfo ──→ error_dialog (SnackBar/AlertDialog)
```

## Notes

- All entities are **immutable** (`frozen=True`) except `ProgressState` which is mutable (updated in-place during pipeline execution).
- No Pydantic — these are internal GUI messages, not API contracts. Plain `dataclass` is simpler (constitution XII: YAGNI).
- `EpisodeResult` and `PipelineRunResult` are mapped from domain `PipelineReport` / `EpisodeReport` — the mapping lives in `bootstrap.py` or a thin mapper function, not in the widgets.
