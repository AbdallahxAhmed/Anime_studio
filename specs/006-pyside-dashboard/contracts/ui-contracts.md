# UI Contracts: PySide6 Dashboard

**Feature**: 006-pyside-dashboard
**Date**: 2026-05-26

## Widget Interface Contracts

### MainWindow

| Property | Type | Description |
|----------|------|-------------|
| title | str | "Anime Studio v3" |
| min_size | (int, int) | (800, 600) |
| default_size | (int, int) | (1100, 800) |
| theme | str | "dark" via qdarktheme |

**Signals Consumed**:
- `SignalBridge.pipeline_finished` → show results table
- `SignalBridge.pipeline_error` → show QMessageBox.critical

**User Actions**:
- Close window → confirmation dialog if pipeline running

---

### LibraryPickerWidget

| Property | Type | Description |
|----------|------|-------------|
| path_display | QLineEdit (read-only) | Shows selected library path |
| browse_button | QPushButton | Opens QFileDialog |

**Signals Emitted**:
- `library_selected(Path)` — when user selects a valid directory

**Signals Consumed**:
- None (self-contained)

---

### ActivityFeedWidget

| Property | Type | Description |
|----------|------|-------------|
| text_area | QTextEdit (read-only) | Scrolling log display |
| max_entries | int | 5000 (oldest trimmed beyond this) |

**Signals Consumed**:
- `SignalBridge.log_received(dict)` → append formatted entry

**Behavior**:
- Auto-scroll when user is at bottom
- Pause auto-scroll when user scrolls up
- Resume auto-scroll when user scrolls to bottom
- Batch updates via QTimer (16ms) for >10 events/sec

---

### ProgressPanelWidget

| Property | Type | Description |
|----------|------|-------------|
| progress_bar | QProgressBar | 0-100% or indeterminate |
| status_label | QLabel | Current phase description |

**Signals Consumed**:
- `SignalBridge.progress_updated(ProgressState)` → update bar + label

**Visual States**:
- IDLE: bar hidden, label "Waiting..."
- SCANNING: indeterminate bar, label "Scanning library..."
- MUXING: determinate bar (0-100%), label "Muxing episode X of Y"
- COMPLETE: bar 100% green, label "Complete!"
- ERROR: bar red, label shows error summary

---

### ResultsTableWidget

| Column | Type | Sortable | Copyable |
|--------|------|----------|----------|
| Name | str | ✅ | ✅ |
| Status | str (✓/⚠/✗) | ✅ | ✅ |
| Fonts Found | int | ✅ | ✅ |
| Fonts Missing | int | ✅ | ✅ |
| Error | str | ✅ | ✅ (tooltip for full text) |

**Signals Consumed**:
- `SignalBridge.pipeline_finished(PipelineRunResult)` → populate rows

**Context Menu**:
- Right-click → "Copy Cell", "Copy Row"
