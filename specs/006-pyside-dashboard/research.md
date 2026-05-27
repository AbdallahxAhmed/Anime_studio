# Research: PySide6 Dashboard

**Feature**: 006-pyside-dashboard
**Date**: 2026-05-26

## 1. PySide6 + qasync Event Loop Integration

**Decision**: Use `qasync.QEventLoop` with `asyncio.run(..., loop_factory=QEventLoop)` (Python 3.11+).

**Rationale**: `qasync` is the mature, standard library for bridging asyncio and Qt. It provides a unified event loop so coroutines and Qt signals coexist on the same thread — no manual thread management. The `@asyncSlot()` decorator is essential for connecting Qt signals to async methods.

**Alternatives Considered**:
- `PySide6.QtAsyncio` (tech preview in 6.6+): Native Qt+asyncio integration but immature/unstable for production.
- `QThread` + `asyncio.run()` per thread: Violates constitution (manual thread creation FORBIDDEN). Creates event loop per thread.
- `asyncio.to_thread()` for everything: Defeats purpose of async-first.

**Key Pitfalls**:
1. **Blocking the main thread** — `time.sleep()` or sync I/O freezes GUI even with qasync. Always `await` or use `run_in_executor`.
2. **Object lifetimes** — if a QObject is garbage collected, its connections die. Keep references as `self.x`.
3. **Scheduling too early** — don't schedule async tasks in `__init__`. Use `QTimer.singleShot(0, ...)` or `showEvent`.
4. **Mixing event loops** — never create a second asyncio loop; `QEventLoop` must be the only one.

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

## 2. Dark Theme Strategy

**Decision**: Dual strategy — try `qdarktheme` first, fall back to `Fusion` + custom `QPalette`.

**Rationale**: `qdarktheme` has reported compatibility issues with PySide6 6.8+ and Python 3.13. However, it remains the simplest single-call dark theme solution. Implementation MUST include a fallback path.

**Primary**: `qdarktheme.setup_theme("dark")` — call after `QApplication()`.

**Fallback** (if qdarktheme import fails or crashes):
```python
app.setStyle("Fusion")
palette = QPalette()
palette.setColor(QPalette.Window, QColor(53, 53, 53))
palette.setColor(QPalette.WindowText, Qt.white)
palette.setColor(QPalette.Base, QColor(25, 25, 25))
# ... (full palette in theme.py)
app.setPalette(palette)
```

**Alternatives Considered**:
- `QDarkStyleSheet`: Less maintained, older aesthetic.
- Qt 6.5+ native `setColorScheme(Qt.ColorScheme.Dark)`: Platform-dependent, inconsistent across Windows versions.
- `qt-material`: Material Design themes, well-maintained but heavier dependency.

## 3. Thread-Safe Async → GUI Signal Bridge

**Decision**: `SignalBridge(QObject)` with custom signals emitted directly from async coroutines inside the `qasync` loop.

**Rationale**: Since `qasync.QEventLoop` merges asyncio INTO the Qt event loop (same thread), `.emit()` can be called directly from `async def` methods. No explicit thread safety mechanism needed beyond signals. The `@asyncSlot()` decorator handles signal→coroutine connections.

**Key Insight**: With qasync, asyncio coroutines run ON the Qt thread. Signal emission is safe. The SignalBridge is about decoupling, not thread safety.

**For existing `GuiLogBridge`** (uses `asyncio.Queue`): Since structlog processors may be called from background threads (via `asyncio.to_thread()`), the existing `call_soon_threadsafe` pattern is correct. The bridge drains the queue via a `QTimer` poll or async loop within the qasync event loop.

**Alternatives Considered**:
- `QMetaObject.invokeMethod` with `Qt.QueuedConnection`: Works but verbose, less Pythonic.
- Direct widget update from coroutine: Works with qasync (same thread) but violates decoupling.

## 4. Activity Feed: QPlainTextEdit

**Decision**: `QPlainTextEdit` (read-only) with `setMaximumBlockCount()` ring buffer and throttled batch updates via `QTimer`.

**Rationale**:
- `QPlainTextEdit` is optimized for plain text — no rich text parsing overhead like `QTextEdit`.
- `setMaximumBlockCount(5000)` provides automatic old-line eviction — built-in ring buffer.
- `appendPlainText()` is O(1).
- `setUndoRedoEnabled(False)` saves memory.
- For color-coded log levels: Use ANSI-like prefix markers (e.g., `[WARNING]`) rather than HTML — keep it plain text.
- Batch via `QTimer(100ms)` = 10 updates/sec max. Good enough for human readability.

**Auto-Scroll with Pause**:
```python
vbar = self.verticalScrollBar()
at_bottom = vbar.value() >= vbar.maximum() - 4
self.appendPlainText(batch_text)
if at_bottom:
    vbar.setValue(vbar.maximum())
```

**Alternatives Considered**:
- `QTextEdit`: Richer formatting but heavier (undo history, HTML parsing). Overkill for log text.
- `QListView` + `QAbstractListModel`: Best raw performance for 100k+ lines/sec. Over-engineered for 10 updates/sec.

## 5. Results Table: QTableView + QAbstractTableModel

**Decision**: `QTableView` with custom `QAbstractTableModel` and `QSortFilterProxyModel` for sorting.

**Rationale**: Revised from initial QTableWidget decision based on research findings:
- **Memory**: Only renders visible rows (virtual scrolling). QTableWidget creates 10-20k `QTableWidgetItem` objects for 1000 rows × columns.
- **Sorting**: `QSortFilterProxyModel` sorts the data list — no widget rearrangement. Much faster.
- **Flexibility**: Custom delegates for cell rendering, filtering, custom copy behavior.
- Marginally more code than QTableWidget but significantly better scaling.

**Copy Support**: Override `keyPressEvent` for Ctrl+C, add context menu via `setContextMenuPolicy(Qt.CustomContextMenu)`.

**Alternatives Considered**:
- `QTableWidget`: Simpler API but creates per-cell QWidgetItems. Acceptable for ≤100 rows.
- `QStandardItemModel`: Middle ground but still creates items per cell.

## 6. Existing Code Reuse Assessment

**Reusable Without Changes**:
- `src/gui/log_bridge.py` — `GuiLogBridge` is framework-agnostic. Uses `asyncio.Queue` + `call_soon_threadsafe`.
- `src/gui/messages.py` — Pure dataclasses. No Flet imports.

**Reusable With Modifications**:
- `src/gui/bootstrap.py` — Composition root pattern is correct. Replace Flet wiring with Qt.

**Must Be Rewritten**:
- `src/__main__.py` — `ft.run()` → `QApplication` + `qasync`.
- `src/gui/app.py` — DELETE, absorbed into `main_window.py`.
- `src/gui/screens/dashboard.py` — Flet controls → Qt widgets.
- `src/gui/widgets/*` — All Flet widgets → Qt widgets.
- `src/gui/styles/` — DELETE, replaced by `theme.py`.
