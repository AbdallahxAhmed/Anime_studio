# Implementation Plan: PySide6 Dashboard

**Branch**: `007-pyside-dashboard` | **Date**: 2026-05-26 | **Spec**: [spec.md](file:///d:/Dev/projects/Anime_studio/specs/006-pyside-dashboard/spec.md)

**Input**: Feature specification from `/specs/006-pyside-dashboard/spec.md`

## Summary

Replace the failed Flet GUI dashboard with a robust PySide6 (Qt for Python) implementation. The dashboard provides: library path selection via `QFileDialog`, real-time activity feed via `asyncio.Queue` → Qt signal bridge, `QProgressBar` for operation tracking, and `QTableWidget` for pipeline results. The asyncio event loop is bridged to Qt via `qasync.QEventLoop`, maintaining a single-threaded concurrency model. All existing hexagonal architecture boundaries are preserved — the GUI layer remains a pure consumer of `PipelineRunner`.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: PySide6, qasync, qdarktheme, structlog, pydantic

**Storage**: `config.toml` (TOML via tomllib) — library path persistence

**Testing**: pytest + pytest-asyncio

**Target Platform**: Windows (primary), Linux/macOS (cross-platform)

**Project Type**: Desktop application (GUI)

**Performance Goals**: <2s launch, <500ms log event latency, 60fps GUI during pipeline runs

**Constraints**: Single asyncio event loop, no direct I/O from GUI layer, thread-safe signal emission

**Scale/Scope**: 1 main window, 4 widget panels, ~500-1000 result rows

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Hexagonal Architecture | ✅ PASS | GUI in `src/gui/`, consumes `PipelineRunner` via DI. No business logic in GUI. |
| II. Cross-Platform | ✅ PASS | PySide6 is cross-platform. `pathlib.Path` everywhere. No hardcoded `.exe`. |
| III. Async-First I/O | ✅ PASS | `qasync.QEventLoop` bridges asyncio ↔ Qt. Single event loop. No manual threads. |
| IV. Structured Error Handling | ✅ PASS | `QMessageBox` for errors (critical/warning/info). No raw tracebacks. |
| V. Plugin Registry | ✅ N/A | No registry changes in GUI layer. |
| VI. Data Safety | ✅ N/A | GUI layer does not touch files directly. |
| VII. Subprocess Lifecycle | ✅ N/A | Handled by adapters, not GUI. |
| VIII. Encoding | ✅ N/A | Handled by core, not GUI. |
| IX. Observability | ✅ PASS | Activity feed shows curated INFO+ events. `QProgressBar` for progress. No raw logs. |
| X-bis. Reports | ✅ N/A | Report generation in core, not GUI. |
| X. Testing | ✅ PASS | GUI widgets testable in isolation. |
| XI. Dependencies | ✅ PASS | PySide6, qasync, qdarktheme all approved in constitution v1.7.0. |
| XII. Simplicity | ✅ PASS | Flat module structure. No premature abstraction. |
| XIII. Distribution | ✅ N/A | No changes to distribution. |

**Forbidden Patterns Check**:
- No `flet` imports ✅
- No `textual` imports ✅
- No `print()` for user output ✅
- No blocking subprocess calls ✅

## Project Structure

### Documentation (this feature)

```text
specs/006-pyside-dashboard/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── __main__.py              # MODIFY: PySide6 entry point (replace Flet)
├── app.py                   # DELETE → replaced by gui/main_window.py
├── gui/
│   ├── __init__.py          # MODIFY: update exports
│   ├── main_window.py       # NEW: QMainWindow-based dashboard
│   ├── bootstrap.py         # MODIFY: wire PySide6 instead of Flet
│   ├── log_bridge.py        # KEEP: asyncio.Queue bridge (framework-agnostic)
│   ├── signals.py           # NEW: Qt custom signals for async→GUI bridge
│   ├── messages.py          # MODIFY: update ErrorInfo.is_critical comment
│   ├── theme.py             # NEW: qdarktheme setup
│   ├── widgets/
│   │   ├── __init__.py      # MODIFY: update exports
│   │   ├── activity_feed.py # REWRITE: QTextEdit-based feed
│   │   ├── progress_panel.py# REWRITE: QProgressBar-based panel
│   │   ├── results_table.py # REWRITE: QTableWidget-based table
│   │   └── library_picker.py# NEW: QFileDialog wrapper widget
│   └── screens/             # DELETE: flatten into main_window.py
│       └── dashboard.py     # DELETE → absorbed into main_window.py

tests/
├── unit/
│   └── gui/
│       ├── test_signals.py      # NEW: signal bridge tests
│       ├── test_activity_feed.py# NEW: feed widget tests
│       └── test_results_table.py# NEW: table widget tests
```

**Structure Decision**: Single project structure (Option 1). GUI components live under `src/gui/` per constitution. Screens directory eliminated — single `main_window.py` replaces `dashboard.py` since there's only one screen.

## Research Decisions

### 1. PySide6 + qasync Integration

**Decision**: Use `qasync.QEventLoop` with `asyncio.run(..., loop_factory=QEventLoop)` (Python 3.11+).

**Rationale**: `qasync` is the mature, standard library for bridging asyncio and Qt. Provides a unified event loop so coroutines and Qt signals coexist on the same thread. The `@asyncSlot()` decorator is essential for connecting Qt signals to async methods.

**Pattern**:
```python
import asyncio, sys
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop, asyncSlot, asyncClose

app = QApplication(sys.argv)
app_close_event = asyncio.Event()
app.aboutToQuit.connect(app_close_event.set)
window = MainWindow()
window.show()
asyncio.run(app_close_event.wait(), loop_factory=QEventLoop)
```

### 2. Async→GUI Signal Bridge

**Decision**: `SignalBridge(QObject)` with custom signals emitted directly from async coroutines inside the `qasync` loop. No `QMetaObject.invokeMethod` needed.

**Rationale**: Since `qasync.QEventLoop` merges asyncio INTO the Qt event loop (same thread), `.emit()` can be called directly from `async def` methods. The `SignalBridge` pattern is about decoupling, not thread safety.

**Pattern**:
```python
class SignalBridge(QObject):
    log_received = Signal(dict)
    progress_updated = Signal(object)
    pipeline_finished = Signal(object)
    pipeline_error = Signal(str)
```

### 3. Activity Feed Widget

**Decision**: `QPlainTextEdit` (read-only) with `setMaximumBlockCount()` ring buffer and throttled batch updates.

**Rationale**: `QPlainTextEdit` is optimized for plain text — no rich text parsing overhead like `QTextEdit`. `setMaximumBlockCount(5000)` auto-evicts old lines. `appendPlainText()` is O(1). `setUndoRedoEnabled(False)` saves memory. For colored log levels, use prefix markers (`[WARNING]`, `[ERROR]`) rather than HTML.

**Batching**: `QTimer(100ms)` = 10 updates/sec max. Check `vbar.value() >= vbar.maximum() - 4` before append for auto-scroll.

### 4. Results Table

**Decision**: `QTableView` with custom `QAbstractTableModel` + `QSortFilterProxyModel`.

**Rationale**: Revised from initial QTableWidget — for 500-1000 rows, QTableView with virtual model is superior. Only renders visible rows. `QSortFilterProxyModel` sorts the data list directly (no widget rearrangement). Custom delegates for cell rendering, filtering, and copy behavior. Marginally more code than QTableWidget but significantly better scaling.

### 5. Dark Theme

**Decision**: Dual strategy — try `qdarktheme` first, fall back to `Fusion` + custom `QPalette`.

**Rationale**: `qdarktheme` has reported compatibility issues with PySide6 6.8+ and Python 3.13. Implementation MUST include a fallback path using `app.setStyle("Fusion")` + dark `QPalette` if `qdarktheme` import fails or crashes. This ensures the app always launches with a dark theme regardless of dependency status.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| — | — | — |
