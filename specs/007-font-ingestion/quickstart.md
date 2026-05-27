# Quickstart: Font Ingestion System

**Feature**: 007-font-ingestion
**Date**: 2026-05-27

## Prerequisites

```bash
# From project root — fonttools is already an approved dependency
uv pip install fonttools
# PySide6, qasync, qdarktheme should already be installed from 006-pyside-dashboard
```

## Smoke Test Scenarios

### 1. System Font Resolution (via Pipeline)

1. Ensure an ASS subtitle file references "Arial" (present on every Windows install)
2. Run the pipeline on a library containing that subtitle
3. ✅ Activity feed shows font resolved via `source="system"`
4. ✅ No network requests made for "Arial"
5. ✅ Font cache does NOT contain a copy of `arial.ttf` (resolve-in-place)
6. ✅ `mkvmerge` receives the absolute path `C:\Windows\Fonts\arial.ttf`

### 2. System Font — Not Found Fallback

1. Ensure an ASS subtitle references "FansubCustomFont9000" (not a system font)
2. Run the pipeline
3. ✅ SystemFontHunter returns no results
4. ✅ Resolution falls through to next hunter in priority order
5. ✅ No error, no circuit breaker trip

### 3. Auto-Discovery from Anime Library

1. Create directory structure:
   ```
   D:\TestAnime\ShowX\
   ├── Episode01.mkv
   ├── Episode01.ass
   └── Fonts\
       ├── CustomFont.ttf
       └── AnotherFont.otf
   ```
2. Set `D:\TestAnime\ShowX\` as library path
3. Click "Run Pipeline"
4. ✅ Activity feed shows "Font ingestion complete: 2 new fonts imported" BEFORE episode analysis starts
5. ✅ Both fonts appear in `font_cache/` with TOML index entries
6. ✅ If "CustomFont" is referenced in the ASS, it resolves from cache (layer 1) during analysis

### 4. Auto-Discovery Deduplication

1. Using the same library from test 3, run the pipeline again
2. ✅ Activity feed shows "Font ingestion: 0 new, 2 skipped (already cached)"
3. ✅ No duplicate entries in TOML index

### 5. Manual Import via Button

1. Launch the application
2. ✅ "Import Fonts" button visible near library picker
3. Click "Import Fonts"
4. ✅ Native folder selection dialog opens
5. Select a folder containing 3 `.ttf` files (2 new, 1 already cached)
6. ✅ Activity feed shows "Font ingestion complete: 2 new, 1 skipped (already cached)"
7. ✅ UI remains responsive during import (no freeze)

### 6. Manual Import — Cancel

1. Click "Import Fonts"
2. Click "Cancel" in the folder dialog
3. ✅ No error, no activity feed entry, no crash

### 7. Drag & Drop — Folder

1. Open file explorer alongside the application
2. Drag a folder containing `.ttf` files over the main window
3. ✅ Green border highlight appears
4. Drop the folder
5. ✅ Border highlight disappears
6. ✅ Activity feed shows ingestion result
7. ✅ Fonts appear in cache

### 8. Drag & Drop — Individual Files

1. Drag individual `.ttf` files from file explorer onto the window
2. ✅ Green border highlight appears
3. Drop files
4. ✅ Ingestion runs, results shown in activity feed

### 9. Drag & Drop — Invalid Content

1. Drag a `.txt` file over the window
2. ✅ No green border highlight (drop rejected)
3. Drag a `.jpg` file over the window
4. ✅ No green border highlight (drop rejected)
5. Attempt to drop
6. ✅ Nothing happens

### 10. Corrupt Font Handling

1. Create a 0-byte file named `corrupt.ttf`
2. Include it in a folder with valid fonts
3. Import via button or drag-drop
4. ✅ Activity feed shows "N new, M skipped, 1 failed"
5. ✅ Application does NOT crash
6. ✅ Valid fonts still imported successfully
7. ✅ Log file contains WARNING with the corrupt file path and error

### 11. Concurrent Import During Pipeline

1. Start a pipeline run
2. While pipeline is running, click "Import Fonts" and select a folder
3. ✅ Both operations run concurrently
4. ✅ Total disk I/O is bounded by shared semaphore
5. ✅ Both complete successfully
