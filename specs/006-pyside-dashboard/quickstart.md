# Quickstart: PySide6 Dashboard

**Feature**: 006-pyside-dashboard
**Date**: 2026-05-26

## Prerequisites

```bash
# Install dependencies (from project root)
uv pip install PySide6 qasync qdarktheme
```

## Launch

```bash
# From project root
python -m src
```

Expected: Dark-themed window appears within 2 seconds with "Anime Studio v3" title bar.

## Smoke Test Scenarios

### 1. Window Launch

1. Run `python -m src`
2. ✅ Dark-themed QMainWindow appears
3. ✅ Window title is "Anime Studio v3"
4. ✅ Window is resizable (min 800×600)
5. ✅ "Select Library" button is visible
6. ✅ "Run Pipeline" button is visible but disabled

### 2. Library Selection

1. Click "Select Library"
2. ✅ Native QFileDialog opens
3. Select any directory
4. ✅ Path appears in the text field
5. ✅ "Run Pipeline" button becomes enabled
6. Close and relaunch
7. ✅ Previously selected path is pre-populated

### 3. Activity Feed (requires valid library)

1. Select a valid anime library path
2. Click "Run Pipeline"
3. ✅ Activity feed starts showing log entries
4. ✅ Entries are color-coded (INFO=default, WARNING=yellow, ERROR=red)
5. ✅ Feed auto-scrolls to latest entry
6. Scroll up manually
7. ✅ Auto-scroll pauses
8. Scroll back to bottom
9. ✅ Auto-scroll resumes

### 4. Progress Tracking

1. During pipeline run:
2. ✅ Progress bar appears for scanning phase (indeterminate)
3. ✅ Progress bar switches to determinate during muxing
4. ✅ Percentage updates smoothly
5. ✅ Completion shows green state

### 5. Results Table

1. After pipeline completes:
2. ✅ Table appears with episode rows
3. ✅ Columns: Name, Status, Fonts Found, Fonts Missing, Error
4. Click column headers
5. ✅ Table sorts by clicked column
6. Right-click a cell
7. ✅ "Copy" context menu appears

### 6. Error Handling

1. Select a non-existent path
2. Click "Run Pipeline"
3. ✅ QMessageBox.critical appears with error message
4. ✅ GUI remains responsive after dismissing dialog

### 7. Close During Pipeline

1. Start a pipeline run
2. Click window close button
3. ✅ Confirmation dialog appears
4. Click "Cancel"
5. ✅ Pipeline continues
6. Click close again, confirm
7. ✅ Application exits cleanly
