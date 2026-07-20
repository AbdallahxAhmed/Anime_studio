# Feature Specification: Pre-Packaging UX (Phase 7)

**Feature Branch**: `009-pre-packaging-ux`

**Created**: 2026-06-06

**Status**: Draft

**Input**: User description: "Selective Run (Tree View) + Export Log File + Scanner temp file filter bug fix — Phase 7 pre-packaging UX polish"

---

## Sub-Feature A: Selective Run (Tree View)

### User Scenarios & Testing

### User Story A1 — Browse Library Tree Before Running Pipeline (Priority: P1)

A user picks their anime library folder (e.g. `D:\Anime\`) and clicks Run. Before the pipeline processes anything, a tree view appears showing all discovered shows and their sub-folders (seasons, movies, OVAs). All items are checked by default. The user reviews the tree, unchecks shows or sub-folders they don't want processed, then clicks "Run Pipeline" to proceed with only the selected content.

**Why this priority**: Core gating requirement — without this, user cannot selectively process. Every other UX improvement depends on this interaction existing.

**Independent Test**: Can be tested by pointing at a library with 3+ shows, unchecking one, running pipeline, and verifying the unchecked show's episodes are not processed.

**Acceptance Scenarios**:

1. **Given** a library with 5 show folders each containing 1+ sub-folders, **When** scan completes and the tree view appears, **Then** all 5 shows appear as top-level nodes with their sub-folders as children, all checked by default.
2. **Given** the tree view is displayed, **When** user unchecks "Hunter x Hunter" parent node, **Then** all children (Season 1, Season 2, Movies) become unchecked. The parent shows an unchecked state.
3. **Given** user unchecks 1 of 3 children under a show, **When** viewing the parent checkbox, **Then** parent shows a partial/tri-state (indeterminate) checkbox.
4. **Given** user clicks "Deselect All", **When** viewing the tree, **Then** all checkboxes are unchecked. "Run Pipeline" button remains enabled but processes zero episodes.
5. **Given** user clicks "Select All" after deselecting some, **When** viewing the tree, **Then** all checkboxes are restored to checked.

---

### User Story A2 — Pipeline Processes Only Selected Folders (Priority: P1)

After the user confirms their selection, the pipeline runs only on episodes within checked folders. Unchecked folders are completely skipped. Progress display shows counts based on selected content only.

**Why this priority**: Directly coupled with A1 — selection is meaningless without filtering.

**Independent Test**: Point at a library with 2 shows (each having 3 episodes). Select only Show A. Run pipeline. Verify: 3 episodes processed, Show B's episodes untouched, progress shows "3 of 3".

**Acceptance Scenarios**:

1. **Given** a library with Show A (3 episodes) and Show B (5 episodes), **When** user unchecks Show B and runs pipeline, **Then** only 3 episodes are processed. Show B's MKVs are not modified.
2. **Given** user selects only Season 2 under Show A, **When** pipeline runs, **Then** only Season 2 episodes are processed. Season 1 and Movies episodes under Show A are skipped.
3. **Given** user deselects all shows and clicks "Run Pipeline", **When** pipeline finishes, **Then** zero episodes are processed. The report reflects zero work done.

---

### User Story A3 — Leaf Nodes Show Episode Counts (Priority: P2)

Each folder node in the tree displays the count of processable episodes (MKV files with matching subtitles) in parentheses, helping users make informed selections.

**Why this priority**: Informational enhancement — tree is functional without it, but counts help user decide.

**Independent Test**: Point at a library. Verify leaf nodes show "(N episodes)" where N matches actual MKV count per folder.

**Acceptance Scenarios**:

1. **Given** Show A has Season 1 with 12 MKVs and Season 2 with 6 MKVs, **When** tree view displays, **Then** Season 1 node shows "(12 episodes)" and Season 2 shows "(6 episodes)".
2. **Given** a show folder with all episodes directly in it (no sub-folders), **When** tree view displays, **Then** the show node itself shows "(N episodes)".

---

### Edge Cases (Sub-Feature A)

- What happens when a show folder contains no MKV files? → Node displayed but with "(0 episodes)", unchecked by default.
- What happens when a show has episodes both directly in the show folder AND in sub-folders? → Show folder gets a leaf-like count for direct episodes, sub-folders shown separately.
- What happens when library has only one show? → Single top-level node, still shown in tree for consistency.
- What happens when library scan finds zero shows? → Tree view shows "No shows found" placeholder. "Run Pipeline" disabled.
- What happens when a show name contains special characters (Arabic, Japanese)? → Displayed as-is in the tree (Qt handles Unicode natively).

---

## Sub-Feature B: Export Log File

### User Scenarios & Testing

### User Story B1 — Export Current Session Log to File (Priority: P1)

A user encounters issues during a pipeline run and wants to share the log with the developer. They click "Export Log" near the Activity Feed, pick a save location via a file dialog, and receive a human-readable plain-text log file of the current session.

**Why this priority**: Primary debugging aid — without this, users must manually copy from Activity Feed or find JSON log files.

**Independent Test**: Run any pipeline operation, click "Export Log", save file, open in text editor — verify readable timestamps, levels, and event data.

**Acceptance Scenarios**:

1. **Given** a session with 50+ log entries, **When** user clicks "Export Log" and selects `D:\Desktop\log.txt`, **Then** a text file is saved with all session entries formatted as `[HH:MM:SS] [LEVEL] event | key=value key=value`.
2. **Given** user saves the log successfully, **When** save completes, **Then** ActivityFeed shows confirmation: "Log exported to D:\Desktop\log.txt".
3. **Given** user clicks "Export Log" but cancels the file dialog, **When** dialog closes, **Then** nothing happens — no error, no confirmation.
4. **Given** the export is triggered during an active pipeline run, **When** file is being written, **Then** the GUI remains responsive (non-blocking I/O).

---

### User Story B2 — Default File Name Suggestion (Priority: P3)

The file save dialog suggests a default filename of `anime_studio_log_YYYY-MM-DD.txt` (using current date), saving users from typing a name.

**Why this priority**: Minor convenience — export works fine without it.

**Independent Test**: Click "Export Log" and verify the default filename in the dialog includes today's date.

**Acceptance Scenarios**:

1. **Given** today is 2026-06-06, **When** Export Log dialog opens, **Then** the suggested filename is `anime_studio_log_2026-06-06.txt`.

---

### Edge Cases (Sub-Feature B)

- What happens when there are zero log entries? → File is created with a header line only: "Anime Studio Session Log — [date]".
- What happens when the target path is read-only? → Standard OS error from file dialog; no crash. ActivityFeed shows "Log export failed: [reason]".
- What happens if user exports twice to the same file? → File is overwritten (standard save dialog behavior — OS prompts overwrite confirmation).

---

## Sub-Feature C: Scanner Temp File Exclusion (Bug Fix)

### User Scenarios & Testing

### User Story C1 — Scanner Ignores Temporary Mux Files (Priority: P1)

During a previous pipeline run, temporary files like `_amux_001.tmp.mkv` may remain if the process was interrupted. The library scanner must skip these files entirely so they don't appear as episodes.

**Why this priority**: Bug fix — temp files cause false scan results and pipeline errors.

**Independent Test**: Place a `_amux_test.tmp.mkv` file in a library folder. Run scan. Verify it does not appear in scan results.

**Acceptance Scenarios**:

1. **Given** a library folder containing `episode01.mkv` and `_amux_ep01.tmp.mkv`, **When** scanner runs, **Then** only `episode01.mkv` appears in results.
2. **Given** a folder contains only `_amux_something.tmp.mkv` files, **When** scanner runs on that folder, **Then** zero episodes are found for that folder.
3. **Given** a file named `amux_regular.mkv` (no leading underscore), **When** scanner runs, **Then** the file IS included (only `_amux_*.tmp.*` pattern is excluded).

---

## Requirements

### Functional Requirements

#### Sub-Feature A: Selective Run

- **FR-A01**: System MUST display a hierarchical tree view of the scanned library AFTER scan completes and BEFORE pipeline processing begins.
- **FR-A02**: Tree MUST have two levels: top-level nodes = direct sub-directories of library root (show folders); second-level nodes = sub-directories within each show folder.
- **FR-A03**: All tree nodes MUST have tri-state checkboxes (checked, unchecked, partially-checked for parents).
- **FR-A04**: All checkboxes MUST default to checked.
- **FR-A05**: Toggling a parent checkbox MUST propagate to all children. Toggling a child MUST update parent to reflect aggregate state.
- **FR-A06**: Leaf nodes MUST display episode count in parentheses: `Show Name (12 episodes)`.
- **FR-A07**: Tree MUST support expand/collapse for show nodes.
- **FR-A08**: "Select All" and "Deselect All" buttons MUST be provided above or beside the tree.
- **FR-A09**: Pipeline MUST accept a set of selected folder paths and process ONLY episodes within those paths.
- **FR-A10**: When `selected_paths` is `None`, pipeline MUST process all episodes (backwards compatibility).
- **FR-A11**: Selection state MUST live in the GUI layer only — not persisted to disk or config.
- **FR-A12**: No business logic (episode filtering, path matching) in the GUI layer — GUI passes paths to core.

#### Sub-Feature B: Export Log

- **FR-B01**: System MUST provide an "Export Log" button in the GUI near the Activity Feed area.
- **FR-B02**: Clicking "Export Log" MUST open a file save dialog for the user to choose save location.
- **FR-B03**: Exported file MUST be plain text with each line formatted as: `[HH:MM:SS] [LEVEL] event | key=value key=value`.
- **FR-B04**: Export MUST include only the current session's log entries, not historical sessions.
- **FR-B05**: File writing MUST be non-blocking (`asyncio.to_thread()`).
- **FR-B06**: After successful export, ActivityFeed MUST show a confirmation message with the full saved file path.
- **FR-B07**: If the user cancels the dialog, no action is taken.
- **FR-B08**: If export fails (I/O error), ActivityFeed MUST show an error message.
- **FR-B09**: No new external dependencies may be introduced.

#### Sub-Feature C: Scanner Temp File Fix

- **FR-C01**: `_is_excluded()` in `library_scanner.py` MUST skip files matching the pattern `_amux_*.tmp.*` (underscore prefix, amux identifier, .tmp extension segment).
- **FR-C02**: Files without the leading underscore MUST NOT be excluded by this rule.

### Key Entities

- **LibraryScanOutput**: Existing model. Gains new field: `show_tree: list[ShowNode]` — hierarchical structure of show folders with sub-folders and episode counts.
- **ShowNode**: New lightweight data structure: `name: str`, `path: Path`, `sub_folders: list[SubFolderNode]`, `direct_episode_count: int`.
- **SubFolderNode**: New lightweight data structure: `name: str`, `path: Path`, `episode_count: int`.
- **PipelineConfig**: Existing model. Gains new optional field: `selected_paths: set[Path] | None = None`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can selectively process a subset of their library in under 10 seconds of interaction (check/uncheck tree nodes).
- **SC-002**: Unchecked shows have zero episodes processed — verified by pipeline report showing no entries for unchecked paths.
- **SC-003**: Users can export a session log to a file in under 5 seconds (button click → save dialog → confirmation).
- **SC-004**: Exported log file is human-readable in any text editor without specialized tooling.
- **SC-005**: Temporary mux files (`_amux_*.tmp.*`) never appear in scan results.
- **SC-006**: All existing 231+ unit tests continue to pass after changes.
- **SC-007**: GUI remains responsive (no freeze) during log export and tree population.

## Assumptions

- Library structure is maximum 2 levels deep (show → sub-folder). Deeper nesting (sub-sub-folders) is flattened or ignored.
- The `GuiLogBridge` already captures all session log entries; export reads from its internal buffer rather than from disk log files.
- PySide6 `QTreeWidget` handles libraries up to 500 shows with sub-second rendering.
- Export log file size is bounded by the 1000-entry cap on ActivityFeed (at most ~100KB).
- `_amux_` prefix is a fixed convention from mux_planner.py and will not change.

## Constitution Compliance Notes

| Requirement | Compliance |
|---|---|
| No business logic in GUI (§I) | ✅ Selection tree is pure presentation; filtering by `selected_paths` happens in `PipelineRunner` |
| No `asyncio.Queue` for Qt UI (§Forbidden) | ✅ Log bridge uses `QtCore.Signal` |
| `pathlib.Path` everywhere (§II) | ✅ `selected_paths: set[Path]`, tree built from `Path` objects |
| `asyncio.to_thread()` for file I/O (§III) | ✅ Log export writes via `asyncio.to_thread()` |
| No new deps (§XII) | ✅ Uses only PySide6 + structlog already in stack |
| Semaphore in core/ only (§Forbidden) | ✅ No new semaphores needed |
| Structured logging (§IX) | ✅ All events use structlog |

## Task Breakdown (for Implementation Agent)

### Sub-Feature A: Selective Run

1. **T-A01**: Add `ShowNode` and `SubFolderNode` dataclasses to `src/models/pipeline.py`
2. **T-A02**: Add `show_tree: list[ShowNode]` field to `LibraryScanOutput`
3. **T-A03**: Modify `LibraryScanner._phase1_walk()` to build `show_tree` from discovered directory structure
4. **T-A04**: Add `selected_paths: set[Path] | None = None` to `PipelineConfig`
5. **T-A05**: Modify `PipelineRunner.run()` to filter `scan_results` by `selected_paths` when not None
6. **T-A06**: Create `src/gui/widgets/selection_tree.py` — `SelectionTreeWidget(QWidget)` wrapping `QTreeWidget`
7. **T-A07**: Wire tree population from `LibraryScanOutput.show_tree` data
8. **T-A08**: Implement tri-state checkbox propagation (parent ↔ child)
9. **T-A09**: Implement `get_selected_paths() -> set[Path]` method on `SelectionTreeWidget`
10. **T-A10**: Add "Select All" / "Deselect All" buttons
11. **T-A11**: Integrate `SelectionTreeWidget` into `MainWindow` layout — show after scan, before pipeline run
12. **T-A12**: Modify `_on_run_click()` to: scan → show tree → wait for user → pass `selected_paths` to `PipelineConfig`
13. **T-A13**: Unit tests for `ShowNode`/`SubFolderNode` models
14. **T-A14**: Unit tests for scanner tree building
15. **T-A15**: Unit tests for `PipelineRunner` filtering by `selected_paths`
16. **T-A16**: Unit tests for `SelectionTreeWidget` (checkbox propagation, get_selected_paths)

### Sub-Feature B: Export Log

17. **T-B01**: Add session log buffer to `GuiLogBridge` — store list of event dicts
18. **T-B02**: Add `format_log_entry(entry: dict) -> str` helper (plain text formatting)
19. **T-B03**: Add `export_session_log(entries: list[dict], path: Path)` async function
20. **T-B04**: Add "Export Log" button to `ActivityFeedWidget` control row
21. **T-B05**: Wire button click → `QFileDialog.getSaveFileName()` → async export → confirmation in ActivityFeed
22. **T-B06**: Unit tests for `format_log_entry` formatting
23. **T-B07**: Unit tests for export function (mock filesystem)

### Sub-Feature C: Scanner Bug Fix

24. **T-C01**: Add temp file pattern check in `_is_excluded()`: `re.match(r"_amux_.*\.tmp\.", filename)`
25. **T-C02**: Unit tests: temp file excluded, normal file included, edge cases
