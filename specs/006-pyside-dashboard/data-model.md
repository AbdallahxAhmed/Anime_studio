# Data Model: PySide6 Dashboard

**Feature**: 006-pyside-dashboard
**Date**: 2026-05-26

## Entities

### Existing (No Changes)

These entities from `src/gui/messages.py` are pure dataclasses with no framework dependency:

| Entity | Location | Purpose |
|--------|----------|---------|
| `ProgressPhase` | `src/gui/messages.py` | Enum: IDLE, SCANNING, MUXING, COMPLETE, ERROR |
| `ProgressState` | `src/gui/messages.py` | Phase + completed/total counts + label |
| `ActivityEntry` | `src/gui/messages.py` | Log event: timestamp, level, category, message, details |
| `EpisodeResult` | `src/gui/messages.py` | Per-episode: name, status, fonts_found/missing, error |
| `EpisodeStatus` | `src/gui/messages.py` | Enum: COMPLETE, PARTIAL, FAILED |
| `PipelineRunResult` | `src/gui/messages.py` | Aggregate: episodes list, duration, report path, totals |
| `ErrorInfo` | `src/gui/messages.py` | Error: title, message, suggestion, is_critical |

### Existing (No Changes — Log Bridge)

| Entity | Location | Purpose |
|--------|----------|---------|
| `GuiLogBridge` | `src/gui/log_bridge.py` | structlog processor → asyncio.Queue. Framework-agnostic. |

### New Entities

| Entity | Location | Purpose |
|--------|----------|---------|
| `SignalBridge` | `src/gui/signals.py` | QObject with typed signals for async→GUI event delivery |

#### SignalBridge

```python
class SignalBridge(QObject):
    """Qt signal hub for async-to-GUI event delivery."""
    log_received = Signal(dict)           # ActivityEntry as dict
    progress_updated = Signal(object)     # ProgressState
    pipeline_finished = Signal(object)    # PipelineRunResult
    pipeline_error = Signal(str)          # Error message string
```

## Relationships

```
PipelineRunner (src/core/)
    ├── emits log events → structlog → GuiLogBridge → asyncio.Queue
    │                                                       │
    │                    ┌──────────────────────────────────┘
    │                    ▼
    │            SignalBridge.log_received.emit(event_dict)
    │                    │
    │                    ▼
    │            ActivityFeedWidget.on_log_received(event_dict)
    │
    ├── emits progress → asyncio callback → SignalBridge.progress_updated.emit()
    │                                              │
    │                                              ▼
    │                                   ProgressPanelWidget.on_progress()
    │
    └── returns PipelineReport → bootstrap maps → SignalBridge.pipeline_finished.emit()
                                                         │
                                                         ▼
                                              ResultsTableWidget.populate()
```

## State Transitions

### ProgressPhase State Machine

```
IDLE ──[pipeline starts]──→ SCANNING
SCANNING ──[scan complete]──→ MUXING
MUXING ──[all episodes done]──→ COMPLETE
SCANNING|MUXING ──[error]──→ ERROR
COMPLETE|ERROR ──[run again]──→ IDLE
```
