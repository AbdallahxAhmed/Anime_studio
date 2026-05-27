# Feature Specification: Font Ingestion System

**Feature Branch**: `008-font-ingestion`

**Created**: 2026-05-27

**Status**: Draft

**Input**: User description: "Create a Font Ingestion System with system font hunting, auto-discovery from anime library Fonts/ dirs, manual import button, drag & drop support, and feedback via SignalBridge to ActivityFeedWidget. Strict Hexagonal Architecture."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - System Font Resolution (Priority: P1)

When the pipeline processes an anime episode, fonts referenced in ASS subtitles that exist on the user's operating system should be automatically discovered and resolved without downloading from the internet.

The System Font Hunter scans standard OS font directories, reads internal font metadata via `fonttools`, and returns a `FontAsset` with the absolute path to the system-installed font. No copying occurs — the font is referenced in-place. The asset is marked `is_cacheable=False` to prevent unnecessary duplication into the permanent cache.

**Why this priority**: System fonts (Arial, Segoe UI, MS Gothic, etc.) are the most commonly referenced fonts in subtitle files. Resolving them locally eliminates unnecessary network requests and speeds up the pipeline dramatically. This is foundational infrastructure that all other ingestion features build upon.

**Independent Test**: Can be fully tested by creating a mock ASS file referencing "Arial" (present on every Windows installation) and verifying the SystemFontHunter resolves it to `C:\Windows\Fonts\arial.ttf` without any network calls or cache writes.

**Acceptance Scenarios**:

1. **Given** a subtitle file referencing "Arial", **When** the font resolution chain executes, **Then** the SystemFontHunter finds `arial.ttf` in the OS font directory, returns a `FontAsset` with `source="system"`, `is_cacheable=False`, and the absolute path, and no cache write occurs.
2. **Given** a subtitle file referencing "NonExistentFont2099", **When** the SystemFontHunter scans all OS font directories, **Then** the hunter returns no result, the circuit breaker is NOT tripped (no network involved), and resolution falls through to the next hunter in priority order.
3. **Given** the application runs on Linux, **When** the SystemFontHunter executes, **Then** it scans `/usr/share/fonts/`, `/usr/local/share/fonts/`, and `~/.local/share/fonts/` instead of Windows paths, with identical behavior.

---

### User Story 2 - Auto-Discovery from Anime Library (Priority: P1)

When the pipeline scans an anime library, it automatically detects any `Fonts/` or `fonts/` directory within the library tree. All `.ttf` and `.otf` files found are async-copied into the permanent font cache before episode analysis begins, ensuring they are immediately available during font resolution.

The library scanner identifies font directories during its directory walk and returns them as part of the scan result. The `PipelineRunner` executes a single pre-pipeline ingestion step to process all discovered directories at once (O(1) ingestion per batch run), preventing redundant disk I/O when multiple episodes share the same font directory.

**Why this priority**: Many anime fansub groups bundle custom fonts alongside their releases. Auto-discovery eliminates the manual step of importing these fonts, making the pipeline truly hands-free for the most common use case.

**Independent Test**: Can be fully tested by creating a temporary directory structure with an anime library containing a `Fonts/` subdirectory with sample `.ttf` files. Run the pipeline scanner and verify the fonts are ingested into the cache before episode analysis starts.

**Acceptance Scenarios**:

1. **Given** an anime library at `D:\Anime\ShowX\` containing `D:\Anime\ShowX\Fonts\CustomFont.ttf`, **When** the pipeline scan phase completes, **Then** the scan result includes `D:\Anime\ShowX\Fonts\` in its font directories list, and the font is copied to `font_cache/CustomFont.ttf` with an updated TOML index entry before any episode analysis begins.
2. **Given** the same library scanned with 24 episodes all under `ShowX\`, **When** the pre-pipeline ingestion step runs, **Then** the `Fonts/` directory is processed exactly once (not 24 times), and the ingestion result reports the correct counts.
3. **Given** a `Fonts/` directory containing a font named "FansubSpecial" that already exists in the cache, **When** the ingestion runs, **Then** the font is skipped (deduplicated by internal font name via `fonttools` nameID lookup), and the result reports it as "skipped (already cached)".
4. **Given** a `fonts/` directory (lowercase), **When** the scanner walks the library, **Then** it is detected and treated identically to `Fonts/` (case-insensitive matching).

---

### User Story 3 - Manual Font Import (Priority: P2)

The user can click an "Import Fonts" button in the main window to manually select a folder containing font files. The selected folder's `.ttf` and `.otf` files are async-ingested into the permanent cache without blocking the UI. Results are displayed in the Activity Feed.

**Why this priority**: Provides a fallback for fonts that aren't in the anime library's `Fonts/` directory and aren't installed system-wide. Important for power users who maintain personal font collections.

**Independent Test**: Can be fully tested by clicking the "Import Fonts" button, selecting a folder with sample fonts via the file dialog, and verifying the activity feed shows "Imported N new fonts, M skipped (already cached), K failed."

**Acceptance Scenarios**:

1. **Given** the main window is displayed, **When** the user clicks "Import Fonts", **Then** a native folder selection dialog opens, and the user can select a directory.
2. **Given** a folder with 10 `.ttf` files is selected (5 new, 3 already cached, 2 corrupt), **When** the ingestion completes, **Then** the Activity Feed displays "Imported 5 new fonts. 3 skipped (already cached). 2 failed." and the cache TOML index is updated atomically.
3. **Given** the user cancels the folder dialog, **When** no folder is selected, **Then** no ingestion runs and no error is displayed.
4. **Given** the pipeline is currently running, **When** the user clicks "Import Fonts", **Then** the import still works concurrently (respecting the disk I/O semaphore) without interfering with the pipeline.

---

### User Story 4 - Drag & Drop Font Import (Priority: P2)

The user can drag a folder or individual font files from their file explorer and drop them onto the main application window. The dropped items trigger the same async ingestion process as the manual import, with results shown in the Activity Feed.

**Why this priority**: Enhances discoverability and reduces friction for font import. A natural complement to the manual import button. Same priority because it uses the exact same core service.

**Independent Test**: Can be fully tested by simulating a drag-drop event with a folder path containing font files and verifying the Activity Feed shows the ingestion result.

**Acceptance Scenarios**:

1. **Given** the main window is displayed, **When** the user drags a folder containing `.ttf`/`.otf` files over the window, **Then** a visual border highlight appears indicating the drop is accepted.
2. **Given** the user drops the folder, **When** the ingestion completes, **Then** the Activity Feed displays the result (new/skipped/failed counts) identically to manual import.
3. **Given** the user drags individual `.ttf` files (not a folder) over the window, **When** they drop the files, **Then** each font file is ingested individually into the cache.
4. **Given** the user drags a non-font item (e.g., a `.txt` file or a folder with no font files), **When** they drag it over the window, **Then** the drop is rejected (no highlight, no ingestion).

---

### User Story 5 - Ingestion Feedback via Activity Feed (Priority: P1)

All font ingestion operations (auto-discovery, manual import, drag & drop) report their results through the `SignalBridge` to the `ActivityFeedWidget`. The feedback includes counts of new fonts ingested, fonts skipped due to deduplication, and fonts that failed to process.

**Why this priority**: Without user-visible feedback, the ingestion system operates as a black box. Users need to know what happened, especially when troubleshooting missing fonts. This is the glue that connects all ingestion triggers to the UI.

**Independent Test**: Can be fully tested by triggering a font ingestion with known inputs and verifying the Activity Feed receives a structured log entry with the correct counts.

**Acceptance Scenarios**:

1. **Given** an ingestion of 15 new fonts completes successfully, **When** the result is emitted, **Then** the Activity Feed displays "Font ingestion complete: 15 new fonts imported" at INFO level.
2. **Given** an ingestion with mixed results (10 new, 5 skipped, 2 failed), **When** the result is emitted, **Then** the Activity Feed displays all three counts in a single entry.
3. **Given** an ingestion where all fonts are already cached, **When** the result is emitted, **Then** the Activity Feed displays "Font ingestion: 0 new, 20 skipped (already cached)" — no false success.
4. **Given** a corrupt `.ttf` file fails to parse with `fonttools`, **When** the failure is recorded, **Then** it is logged at WARNING level with the file path and error reason, and the overall ingestion continues (no crash).

---

### Edge Cases

- What happens when `C:\Windows\Fonts` is inaccessible due to permissions? → SystemFontHunter logs WARNING, returns empty results, resolution falls through to next hunter.
- What happens when a font file is locked by another process during copy? → `FontIngestionService` catches the `PermissionError`, records it as a failed file, continues with remaining fonts.
- What happens when the `font_cache` directory is on a full disk? → Atomic write fails, `FontIngestionService` catches `OSError`, reports failure count, does not corrupt the TOML index.
- What happens when a `.ttf` file has zero-length or is truncated? → `fonttools` raises an exception during nameID read, file is counted as "failed" with the reason logged.
- What happens when `Fonts/` directory contains nested subdirectories? → Scanner recursively walks subdirectories to find all `.ttf`/`.otf` files.
- What happens when the same font file is dropped twice in rapid succession? → Second ingestion detects the name already in cache (from the first run), skips it, reports as "skipped."
- What happens when the user drops 500+ fonts at once? → Ingestion processes them concurrently via `asyncio.to_thread()` with the disk I/O semaphore limiting concurrent copies.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement a `SystemFontHunter` that conforms to `HunterProtocol` and scans standard OS font directories cross-platform (Windows: `C:\Windows\Fonts`, `~\AppData\Local\Microsoft\Windows\Fonts`; Linux: `/usr/share/fonts/`, `/usr/local/share/fonts/`, `~/.local/share/fonts/`; macOS: `~/Library/Fonts/`, `/Library/Fonts/`, `/System/Library/Fonts/`).
- **FR-002**: `SystemFontHunter` MUST use `fonttools` to read internal font names (nameID 1, 4, 16) and match them against the `FontQuery.requested_name`, not by filename.
- **FR-003**: `SystemFontHunter` MUST return `FontAsset` with `is_cacheable=False` and the absolute path to the system font. No file copying.
- **FR-004**: `SystemFontHunter` MUST be registered in `HunterRegistry` with a priority placing it between the local cache and network hunters (e.g., priority 4, consistent with spec 003 Layer 4).
- **FR-005**: `FontAsset` domain model MUST be extended with an `is_cacheable: bool = True` field. The pipeline MUST respect this flag and skip cache writes when `False`.
- **FR-006**: System MUST implement a `FontIngestionService` in the core layer that accepts a list of directory paths or file paths, scans them for `.ttf`/`.otf` files, deduplicates by internal font name (via `fonttools`), and async-copies new fonts to the permanent font cache.
- **FR-007**: `FontIngestionService` MUST return a `FontIngestionResult` containing `success_count`, `skipped_count`, `failed_count`, and `failed_details: list[tuple[Path, str]]`.
- **FR-008**: The library scanner MUST detect `Fonts/` and `fonts/` directories (case-insensitive) during its directory walk and include them in the scan result as `font_directories: list[Path]`.
- **FR-009**: `PipelineRunner.run()` MUST execute `FontIngestionService.ingest_directories()` as a pre-pipeline step after the scan phase and before the analysis loop. All discovered font directories MUST be deduplicated before ingestion.
- **FR-010**: The `MainWindow` MUST include an "Import Fonts" `QPushButton` positioned near the library picker in the config group. Clicking it MUST open a `QFileDialog.getExistingDirectory()` and trigger `FontIngestionService` asynchronously via `qasync`.
- **FR-011**: The `MainWindow` MUST accept drag-and-drop via `setAcceptDrops(True)`. Valid drops (folders or `.ttf`/`.otf` files) MUST trigger `FontIngestionService` asynchronously. Invalid drops MUST be rejected. A visual border highlight MUST appear during valid drag-over.
- **FR-012**: All ingestion results MUST be emitted as structured log events via `structlog` with fields `event="font_ingestion_complete"`, `success_count`, `skipped_count`, `failed_count`, and `source` (one of: "auto_discovery", "manual_import", "drag_drop"). These events flow through `GuiLogBridge` → `SignalBridge.log_received` → `ActivityFeedWidget`.
- **FR-013**: All file copy operations MUST use `asyncio.to_thread(shutil.copy2, ...)` wrapped with the application-scoped disk I/O `asyncio.Semaphore`.
- **FR-014**: Font name deduplication MUST use `fonttools` to read nameID from the source file and compare against existing cache entries. Files whose font name already exists in the cache MUST be skipped without error.
- **FR-015**: The TOML cache index MUST be updated atomically after each batch ingestion (not per-file) to minimize I/O.

### Key Entities

- **FontIngestionService**: Core service orchestrating font discovery, deduplication, copy, and catalog rebuild. Pure async, no UI dependency. Injected with `FontCache` and `FilesystemAdapter`.
- **FontIngestionResult**: Value object returned by ingestion operations. Contains `success_count: int`, `skipped_count: int`, `failed_count: int`, `failed_details: list[tuple[Path, str]]`, `source: str`.
- **SystemFontHunter**: `HunterProtocol` implementation for cross-platform OS font discovery. Uses `fonttools` for nameID matching. Returns non-cacheable `FontAsset` objects.
- **FontAsset** (extended): Existing model gains `is_cacheable: bool = True` field to distinguish system-resolved fonts from cached fonts.
- **LibraryScanResult** (extended): Existing model gains `font_directories: list[Path]` field to carry discovered font directories to the pipeline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Fonts installed on the user's operating system are resolved within 2 seconds per font without any network requests.
- **SC-002**: Fonts bundled in an anime library's `Fonts/` directory are automatically available for resolution during the same pipeline run that discovers them, with zero user intervention.
- **SC-003**: Manual font import from a folder of 100 fonts completes within 30 seconds, including deduplication and cache catalog rebuild.
- **SC-004**: Users receive clear, itemized feedback (new/skipped/failed counts) in the Activity Feed within 1 second of ingestion completion.
- **SC-005**: Drag-and-drop font import works identically to manual import, with visual feedback during the drag operation.
- **SC-006**: The ingestion system handles corrupt or unreadable font files gracefully — zero crashes, with each failure individually reported.
- **SC-007**: Auto-discovery processes each unique font directory exactly once per pipeline run, regardless of the number of episodes sharing that directory.

## Assumptions

- Users have read access to their OS font directories (e.g., `C:\Windows\Fonts`). If access is restricted by enterprise policy, the SystemFontHunter gracefully returns no results.
- The permanent font cache at `D:\Entertainment\.anime_studio\font_cache\` (or OS equivalent) has sufficient disk space for ingested fonts. Disk-full scenarios are handled as failures, not crashes.
- `fonttools` can read nameID metadata from all valid `.ttf`/`.otf` files. Files that `fonttools` cannot parse are treated as corrupt and skipped.
- The existing `FontCache`, `HunterRegistry`, `SignalBridge`, and `FilesystemAdapter` APIs are stable and do not require breaking changes — only additive extensions.
- The `PipelineRunner` scan phase already walks the full library directory tree. Adding font directory detection is an incremental enhancement, not a restructuring.
- `.woff` and `.woff2` files are excluded from ingestion — these are web font formats not used by ASS subtitle renderers or `mkvmerge`.
