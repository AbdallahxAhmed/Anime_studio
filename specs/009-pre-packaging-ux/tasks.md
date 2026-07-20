# Tasks: Pre-Packaging UX (Phase 7)

**Input**: Design documents from `specs/009-pre-packaging-ux/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

**Tests**: Included — spec requires tests alongside each component.

**Organization**: Tasks grouped by wave (dependency-ordered), then by user story. Each task specifies exact file, dependencies, and relevant constitution constraint.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US-A1..A3, US-B1..B2, US-C1)
- Exact file paths in descriptions
- `depends:` notation for task ordering

## Path Conventions

```
src/models/pipeline.py          — ShowNode, SubFolderNode, PipelineConfig changes
src/core/library_scanner.py     — _is_excluded() fix, _build_show_tree()
src/core/pipeline_runner.py     — selected_paths filtering
src/gui/log_bridge.py           — Session buffer, format/export helpers
src/gui/widgets/selection_tree.py — [NEW] SelectionTreeWidget
src/gui/widgets/activity_feed.py — Export Log button
src/gui/widgets/__init__.py     — Export SelectionTreeWidget
src/gui/main_window.py          — Two-phase run flow, export wiring
```

---

## Phase 1: Bug Fix — Scanner Temp File Filter (Wave 0)

**Purpose**: Fix scanner picking up `_amux_*.tmp.*` temp files. One-line fix, unblocks all testing.

- [x] T001 [US-C1] Add `_AMUX_TEMP_RE = re.compile(r'^_amux_.*\.tmp\.\w+$')` at module level and extend `_is_excluded()` to reject matching filenames in `src/core/library_scanner.py`
  - **File**: `src/core/library_scanner.py` (lines 93-99)
  - **Constitution**: §VI Data Safety — scanner exclusion filter
  - **Details**: Add compiled regex at module level (near line 7). In `_is_excluded()`, after the dot-prefix check, add: `if path.is_file() and _AMUX_TEMP_RE.match(path.name): return True`. Pattern: `^_amux_.*\.tmp\.\w+$` (leading underscore, amux identifier, `.tmp.` segment, final extension). Case-insensitive not needed — convention is lowercase.

- [x] T002 [US-C1] Write unit tests for `_amux_` temp file exclusion in `tests/unit/core/test_library_scanner.py`
  - **File**: `tests/unit/core/test_library_scanner.py`
  - **depends**: T001
  - **Tests**:
    - `test_is_excluded_amux_temp_file` — `_amux_ep01.tmp.mkv` → excluded
    - `test_is_excluded_amux_temp_ass` — `_amux_ep01.tmp.ass` → excluded
    - `test_not_excluded_amux_no_underscore_prefix` — `amux_regular.mkv` → NOT excluded
    - `test_not_excluded_normal_tmp` — `episode.tmp.mkv` → NOT excluded (no `_amux_` prefix)
    - `test_not_excluded_normal_mkv` — `episode01.mkv` → NOT excluded

**Checkpoint**: `uv run pytest tests/unit/core/test_library_scanner.py -v -k "amux"` — all pass. 231+ existing tests still green.

---

## Phase 2: Foundational Models (Wave 1)

**Purpose**: New domain models that all subsequent scanner, runner, and GUI work depends on.

**⚠️ CRITICAL**: No scanner tree building, no PipelineRunner filtering, no SelectionTreeWidget work can begin until this phase completes.

- [x] T003 [P] Add `SubFolderNode` frozen Pydantic model to `src/models/pipeline.py`
  - **File**: `src/models/pipeline.py`
  - **Constitution**: §I — Domain Models in `src/models/`, pure data, zero I/O
  - **Details**: Insert BEFORE `LibraryScanOutput` class. Fields: `name: str = Field(min_length=1)`, `path: SerializablePath`, `episode_count: int = Field(ge=0, default=0)`. Use `model_config = ConfigDict(frozen=True)`.

- [x] T004 [P] Add `ShowNode` frozen Pydantic model to `src/models/pipeline.py`
  - **File**: `src/models/pipeline.py`
  - **depends**: T003 (SubFolderNode referenced in type)
  - **Constitution**: §I — Domain Models in `src/models/`, pure data, zero I/O
  - **Details**: Insert AFTER `SubFolderNode`, BEFORE `LibraryScanOutput`. Fields: `name: str = Field(min_length=1)`, `path: SerializablePath`, `sub_folders: list[SubFolderNode] = Field(default_factory=list)`, `direct_episode_count: int = Field(ge=0, default=0)`.

- [x] T005 Add `show_tree: list[ShowNode]` field to `LibraryScanOutput` in `src/models/pipeline.py`
  - **File**: `src/models/pipeline.py` (class `LibraryScanOutput`, ~line 75)
  - **depends**: T004
  - **Constitution**: §I — backward compatible addition
  - **Details**: Add `show_tree: list[ShowNode] = Field(default_factory=list)` after `font_directories` field. Default empty list ensures backward compatibility — existing code never touches this field.

- [x] T006 Add `selected_paths: frozenset[SerializablePath] | None = None` to `PipelineConfig` in `src/models/pipeline.py`
  - **File**: `src/models/pipeline.py` (class `PipelineConfig`, ~line 66)
  - **depends**: None (independent of ShowNode)
  - **Constitution**: §I — PipelineConfig is frozen (`ConfigDict(frozen=True)`) so MUST use `frozenset` not `set`
  - **Details**: Add `selected_paths: frozenset[SerializablePath] | None = None` after `anime_title` field. `None` means "process all" (default behavior unchanged). Import note: `frozenset` works natively with Pydantic v2 frozen models.

- [x] T007 Write unit tests for `ShowNode`, `SubFolderNode`, and updated `LibraryScanOutput`/`PipelineConfig` in `tests/unit/models/test_pipeline.py`
  - **File**: `tests/unit/models/test_pipeline.py`
  - **depends**: T003, T004, T005, T006
  - **Tests**:
    - `test_sub_folder_node_creation` — valid construction
    - `test_sub_folder_node_frozen` — mutation raises error
    - `test_sub_folder_node_name_min_length` — empty name raises ValidationError
    - `test_show_node_creation` — valid with sub_folders
    - `test_show_node_no_sub_folders` — valid with empty list
    - `test_show_node_frozen` — mutation raises error
    - `test_library_scan_output_with_show_tree` — includes show_tree field
    - `test_library_scan_output_backward_compat` — construction without show_tree still works
    - `test_pipeline_config_selected_paths_none` — default is None
    - `test_pipeline_config_selected_paths_frozenset` — accepts frozenset[Path]
    - `test_pipeline_config_selected_paths_not_set` — `set[Path]` should be coerced or work via Pydantic

**Checkpoint**: `uv run pytest tests/unit/models/test_pipeline.py -v -k "ShowNode or SubFolderNode or selected_paths"` — all pass.

---

## Phase 3: Core Services — Scanner + Log Bridge (Wave 2, parallel tracks)

**Purpose**: Scanner builds `show_tree` from directory structure. Log bridge gains session buffer for export.

### Track A: Scanner Tree Building

- [x] T008 [US-A1] Add `_build_show_tree()` method to `LibraryScanner` class in `src/core/library_scanner.py`
  - **File**: `src/core/library_scanner.py`
  - **depends**: T005 (ShowNode/SubFolderNode models must exist)
  - **Constitution**: §III — uses `asyncio.to_thread()` for filesystem `iterdir()` calls; §I — core/ imports models/ only
  - **Details**: New private method `_build_show_tree(self, lib_path: Path, scan_results: list[LibraryScanResult]) -> list[ShowNode]`. Logic:
    1. Build `episodes_by_dir: dict[Path, int]` counting episodes per parent directory from `scan_results`
    2. Iterate top-level dirs of `lib_path` (skip excluded via `_is_excluded()`)
    3. For each show dir, iterate sub-dirs → create `SubFolderNode` with episode count
    4. Create `ShowNode` with `direct_episode_count` for episodes directly in show dir
    5. Return sorted list of `ShowNode`
  - Import `ShowNode`, `SubFolderNode` from `src.models.pipeline`

- [x] T009 [US-A1] Wire `_build_show_tree()` into `scan()` method and populate `show_tree` in `LibraryScanOutput` in `src/core/library_scanner.py`
  - **File**: `src/core/library_scanner.py` (method `scan()`, ~line 161)
  - **depends**: T008
  - **Details**: After `all_results` is built (line 179), call `show_tree = await asyncio.to_thread(self._build_show_tree, lib_path, all_results)`. Pass `show_tree=show_tree` to `LibraryScanOutput` constructor.

- [x] T010 [US-A1] Write unit tests for scanner `_build_show_tree()` in `tests/unit/core/test_library_scanner.py`
  - **File**: `tests/unit/core/test_library_scanner.py`
  - **depends**: T009
  - **Tests** (use `tmp_path` fixture to create directory structures):
    - `test_build_show_tree_basic` — 2 shows, each with 2 sub-folders → correct ShowNode/SubFolderNode tree
    - `test_build_show_tree_flat_show` — show with episodes directly (no sub-folders) → `direct_episode_count` set, `sub_folders` empty
    - `test_build_show_tree_mixed` — show with both direct episodes and sub-folders → both counts correct
    - `test_build_show_tree_empty_library` — empty dir → empty list
    - `test_build_show_tree_excludes_dot_dirs` — `.git/` not in tree
    - `test_scan_output_includes_show_tree` — full async `scan()` call returns populated `show_tree`

### Track B: Log Bridge Session Buffer (parallel with Track A)

- [x] T011 [P] [US-B1] Add session buffer to `GuiLogBridge` in `src/gui/log_bridge.py`
  - **File**: `src/gui/log_bridge.py`
  - **depends**: None (independent of all Wave 1 work)
  - **Constitution**: §I — GUI layer, no business logic; uses `QtCore.Signal` not `asyncio.Queue`
  - **Details**:
    1. Add `MAX_SESSION_BUFFER = 10000` class constant
    2. In `__init__()`: add `self._session_buffer: list[dict[str, Any]] = []`
    3. In `__call__()`: after `self.log_received.emit(event_copy)`, append: `if len(self._session_buffer) < self.MAX_SESSION_BUFFER: self._session_buffer.append(event_copy)`
    4. Add `def get_session_entries(self) -> list[dict[str, Any]]: return list(self._session_buffer)`

**Checkpoint**: `uv run pytest tests/unit/ -v` — all existing 231+ tests + new tests pass.

---

## Phase 4: Core Services — Runner Filter + Log Export (Wave 3, parallel tracks)

**Purpose**: PipelineRunner filters by `selected_paths`. Log format/export functions created.

### Track A: PipelineRunner Filtering

- [x] T012 [US-A2] Add `_is_ancestor()` helper and `selected_paths` filtering to `PipelineRunner.run()` in `src/core/pipeline_runner.py`
  - **File**: `src/core/pipeline_runner.py`
  - **depends**: T006 (PipelineConfig has `selected_paths` field)
  - **Constitution**: §I — business logic in core/ only, not GUI
  - **Details**:
    1. Add module-level helper (near line 25):
       ```python
       def _is_ancestor(ancestor: Path, descendant: Path) -> bool:
           try:
               descendant.relative_to(ancestor)
               return True
           except ValueError:
               return False
       ```
    2. In `run()`, after `scan_results = scan_output.episodes` (line 62), insert:
       ```python
       if pipeline_config.selected_paths is not None:
           selected = pipeline_config.selected_paths
           original_count = len(scan_results)
           scan_results = [
               ep for ep in scan_results
               if any(_is_ancestor(sel, ep.episode_path) for sel in selected)
           ]
           logger.info(
               "Filtered episodes by selected paths",
               selected_count=len(scan_results),
               total_count=original_count,
               selected_paths_count=len(selected),
           )
       ```
    3. Also store `scan_output` for returning `show_tree` to GUI (add to return value or make accessible via signal).

- [x] T013 [US-A2] Write unit tests for `selected_paths` filtering in `tests/unit/core/test_pipeline_runner.py`
  - **File**: `tests/unit/core/test_pipeline_runner.py`
  - **depends**: T012
  - **Tests** (mock all dependencies):
    - `test_run_selected_paths_none_processes_all` — `selected_paths=None` → all episodes processed
    - `test_run_selected_paths_subset` — `selected_paths=frozenset({show_a_path})` → only show_a episodes
    - `test_run_selected_paths_empty_set` — `selected_paths=frozenset()` → zero episodes processed
    - `test_is_ancestor_true` — `D:\Anime\Show` is ancestor of `D:\Anime\Show\S1\ep01.mkv`
    - `test_is_ancestor_false` — `D:\Anime\ShowA` is NOT ancestor of `D:\Anime\ShowB\ep01.mkv`
    - `test_is_ancestor_same_path` — `D:\Anime\Show` is ancestor of `D:\Anime\Show\ep01.mkv`

### Track B: Log Format and Export (parallel with Track A)

- [x] T014 [P] [US-B1] Add `format_log_entry()` function to `src/gui/log_bridge.py`
  - **File**: `src/gui/log_bridge.py`
  - **depends**: T011 (log bridge has buffer)
  - **Constitution**: None directly — pure formatting function
  - **Details**: Standalone function (not method):
    ```python
    def format_log_entry(entry: dict[str, Any]) -> str:
        """[HH:MM:SS] [LEVEL] event | key=value key=value"""
    ```
    - Parse ISO timestamp → extract `HH:MM:SS` (split on `T`, take time part, strip fractional/timezone)
    - Fallback to `??:??:??` if unparsable
    - Level: uppercase
    - Extra keys: sort alphabetically, skip internal keys (`timestamp`, `level`, `event`, `logger`, `_record`, `_logger`)
    - Format: `[{time}] [{LEVEL}] {event} | k1=v1 k2=v2` (no pipe if no extras)

- [x] T015 [P] [US-B1] Add `export_session_log()` async function to `src/gui/log_bridge.py`
  - **File**: `src/gui/log_bridge.py`
  - **depends**: T014
  - **Constitution**: §III — `asyncio.to_thread()` for file write (never block GUI event loop)
  - **Details**:
    ```python
    async def export_session_log(entries: list[dict[str, Any]], path: Path) -> None:
    ```
    - Build header: `"Anime Studio Session Log — {date}"`
    - Format each entry via `format_log_entry()`
    - Join with `\n`, write to file via `asyncio.to_thread()`
    - `open(path, "w", encoding="utf-8")` — constitution §II mandates explicit encoding

- [x] T016 [P] [US-B1] Write unit tests for `format_log_entry()` in `tests/unit/gui/test_log_export.py`
  - **File**: `tests/unit/gui/test_log_export.py` [NEW]
  - **depends**: T014
  - **Tests**:
    - `test_format_basic_info` — INFO event with timestamp → `[12:34:56] [INFO] something happened`
    - `test_format_with_extras` — event with `stage=scan`, `count=5` → `... | count=5 stage=scan`
    - `test_format_missing_timestamp` — no timestamp → `[??:??:??]`
    - `test_format_error_level` — level=error → `[ERROR]`
    - `test_format_skips_internal_keys` — `_record`, `logger` not in output

- [x] T017 [P] [US-B1] Write unit tests for `export_session_log()` in `tests/unit/gui/test_log_export.py`
  - **File**: `tests/unit/gui/test_log_export.py`
  - **depends**: T015, T016
  - **Tests**:
    - `test_export_writes_file` — export 3 entries → file exists with 3 formatted lines + header
    - `test_export_empty_entries` — export empty list → file has header only
    - `test_export_utf8_encoding` — file opened with `encoding="utf-8"` (verify content)
    - `test_export_async` — `await export_session_log()` completes without blocking

**Checkpoint**: `uv run pytest tests/unit/ -v -k "format_log or export_session or selected_paths or is_ancestor"` — all pass.

---

## Phase 5: GUI — SelectionTreeWidget (Wave 4)

**Purpose**: Build the complete `SelectionTreeWidget` with tri-state checkboxes, expand/collapse, Select All/Deselect All. Longest single phase.

**Goal**: User sees hierarchical tree of shows/seasons after scan, can check/uncheck, and `get_selected_paths()` returns the correct `set[Path]`.

**Independent Test**: Create widget programmatically, call `populate()` with mock ShowNodes, verify checkbox states and `get_selected_paths()`.

- [x] T018 [US-A1] Create `SelectionTreeWidget` class skeleton in `src/gui/widgets/selection_tree.py` [NEW]
  - **File**: `src/gui/widgets/selection_tree.py` [NEW]
  - **depends**: T004 (ShowNode model exists)
  - **Constitution**: §I — GUI layer, pure presentation, no business logic; uses PySide6 exclusively (§Forbidden: no flet/textual/curses)
  - **Details**:
    1. Create `class SelectionTreeWidget(QWidget)` with `QVBoxLayout`
    2. Add `QTreeWidget` with 2 columns: `["Show / Folder", "Episodes"]`
    3. Add `QPushButton("Select All")` and `QPushButton("Deselect All")` in `QHBoxLayout` above tree
    4. Connect buttons to `_select_all()` / `_deselect_all()` stubs
    5. Imports: `from PySide6.QtCore import Qt`, `from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget`

- [x] T019 [US-A1] Implement `populate(show_tree: list[ShowNode])` method in `src/gui/widgets/selection_tree.py`
  - **File**: `src/gui/widgets/selection_tree.py`
  - **depends**: T018
  - **Details**:
    1. `self.tree.blockSignals(True)` before populating, `blockSignals(False)` after
    2. `self.tree.clear()` to reset
    3. For each `ShowNode`: create `QTreeWidgetItem(self.tree)` as top-level
       - `setText(0, show.name)`, `setData(0, Qt.ItemDataRole.UserRole, str(show.path))`
       - Set flags: `item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate`
       - **CRITICAL**: Use `Qt.ItemFlag.ItemIsAutoTristate` (NOT `ItemIsUserTristate`) — auto-propagates parent↔child
       - `setCheckState(0, Qt.CheckState.Checked)` — default all checked
    4. For each `SubFolderNode` in `show.sub_folders`: create `QTreeWidgetItem(show_item)` as child
       - `setText(0, sub.name)`, `setText(1, f"{sub.episode_count} episodes")`
       - `setData(0, Qt.ItemDataRole.UserRole, str(sub.path))`
       - Flags: `item.flags() | Qt.ItemFlag.ItemIsUserCheckable` (NO auto-tristate on leaves)
       - `setCheckState(0, Qt.CheckState.Checked)`
    5. Set episode count text on show item: total = `direct_episode_count + sum(sub.episode_count)`
    6. `show_item.setExpanded(True)` — all expanded by default
    7. `self.tree.resizeColumnToContents(0)`

- [x] T020 [US-A1] Implement `get_selected_paths() -> set[Path]` method in `src/gui/widgets/selection_tree.py`
  - **File**: `src/gui/widgets/selection_tree.py`
  - **depends**: T019
  - **Details**:
    1. Iterate `self.tree.invisibleRootItem().child(i)` for all top-level items
    2. For shows with NO sub-folders (childCount == 0): if checked → add show path
    3. For shows WITH sub-folders: iterate children, add checked child paths
    4. Also add show path itself if show has `direct_episode_count > 0` and parent is not fully unchecked
    5. Path extracted via `Path(item.data(0, Qt.ItemDataRole.UserRole))`
    6. Return `set[Path]`

- [x] T021 [US-A1] Implement `_select_all()` and `_deselect_all()` methods in `src/gui/widgets/selection_tree.py`
  - **File**: `src/gui/widgets/selection_tree.py`
  - **depends**: T018
  - **Details**:
    1. `blockSignals(True)` before, `blockSignals(False)` after
    2. Recursive helper `_set_check_recursive(item, state)`: set item check state, recurse children
    3. Iterate all top-level items, call recursive helper with `Qt.CheckState.Checked` or `Qt.CheckState.Unchecked`

- [x] T022 [US-A1] Export `SelectionTreeWidget` from `src/gui/widgets/__init__.py`
  - **File**: `src/gui/widgets/__init__.py`
  - **depends**: T018
  - **Details**: Add `from src.gui.widgets.selection_tree import SelectionTreeWidget` and add to `__all__` list.

- [x] T023 [US-A1] Write unit tests for `SelectionTreeWidget` in `tests/unit/gui/test_selection_tree.py` [NEW]
  - **File**: `tests/unit/gui/test_selection_tree.py` [NEW]
  - **depends**: T019, T020, T021
  - **Constitution**: §X — unit tests alongside each component
  - **Tests** (need `QApplication` fixture — check if conftest.py has one, add if not):
    - `test_populate_creates_tree_items` — 2 shows, each with 2 sub-folders → 2 top-level, 4 children
    - `test_populate_default_all_checked` — after populate, all items checked
    - `test_populate_episode_counts` — column 1 text shows correct counts
    - `test_populate_show_expanded` — all show items expanded
    - `test_get_selected_paths_all_checked` — returns all paths
    - `test_get_selected_paths_one_show_unchecked` — uncheck show → its paths not in result
    - `test_get_selected_paths_partial_sub_folders` — uncheck 1 sub-folder → only that path missing
    - `test_select_all_after_deselect` — deselect all → select all → all checked
    - `test_deselect_all` — deselect → get_selected_paths returns empty set
    - `test_populate_flat_show_no_sub_folders` — show with direct episodes only → single node
    - `test_auto_tristate_parent` — uncheck 1 of 3 children → parent shows PartiallyChecked

**Checkpoint**: `uv run pytest tests/unit/gui/test_selection_tree.py -v` — all pass.

---

## Phase 6: GUI — Export Log Button (Wave 5, can overlap with Wave 4)

**Purpose**: Add "Export Log" button to ActivityFeed and wire it to the export function.

- [x] T024 [US-B1] Add `export_requested` Signal and "Export Log" button to `ActivityFeedWidget` in `src/gui/widgets/activity_feed.py`
  - **File**: `src/gui/widgets/activity_feed.py`
  - **depends**: T015 (export function exists)
  - **Constitution**: §I — GUI pure presentation; signal decouples from export logic
  - **Details**:
    1. Add `from PySide6.QtCore import Signal` to imports (add to existing `from PySide6.QtCore import ...` if any)
    2. Add class-level: `export_requested = Signal()`
    3. In `__init__()`, add `self.export_button = QPushButton("Export Log", self)` after `self.clear_button`
    4. Add `self.export_button.clicked.connect(self._on_export_click)`
    5. Add `control_layout.addWidget(self.export_button)` — insert BEFORE `control_layout.addWidget(self.clear_button)` (or after, user preference)
    6. Add method:
       ```python
       def _on_export_click(self) -> None:
           self.export_requested.emit()
       ```

- [x] T025 [US-B1] Write unit test for export button existence and signal emission in `tests/unit/gui/test_log_export.py`
  - **File**: `tests/unit/gui/test_log_export.py`
  - **depends**: T024
  - **Tests**:
    - `test_activity_feed_has_export_button` — widget has `export_button` attribute
    - `test_export_button_emits_signal` — click button → `export_requested` signal emitted (use `QSignalSpy` or `mock`)

**Checkpoint**: `uv run pytest tests/unit/gui/test_log_export.py -v` — all pass.

---

## Phase 7: MainWindow Integration (Wave 6 — LAST)

**Purpose**: Wire SelectionTreeWidget into MainWindow layout. Implement two-phase run flow. Wire export log button to handler.

**⚠️ CRITICAL**: This phase depends on ALL previous phases completing. Do NOT start until Waves 0-5 are done.

- [x] T026 [US-A1] Add `SelectionTreeWidget` to `MainWindow` layout in `src/gui/main_window.py`
  - **File**: `src/gui/main_window.py`
  - **depends**: T022 (widget exported), T009 (scanner builds tree), T012 (runner filters)
  - **Constitution**: §I — GUI pure consumer of core services via signals/slots
  - **Details**:
    1. Import `SelectionTreeWidget` from `src.gui.widgets`
    2. In `__init__()`, create `self.selection_tree = SelectionTreeWidget(left_widget)`
    3. Insert into `left_layout` between `config_group` and `activity_feed`: `left_layout.addWidget(self.selection_tree)`
    4. Initially hidden: `self.selection_tree.setVisible(False)`
    5. Store log_bridge reference: `self._log_bridge = log_bridge`
    6. Add state variables: `self._awaiting_selection = False`, `self._pending_scan_output = None`

- [x] T027 [US-A1] Implement two-phase `_on_run_click()` flow in `src/gui/main_window.py`
  - **File**: `src/gui/main_window.py` (method `_on_run_click()`, ~line 147)
  - **depends**: T026
  - **Constitution**: §I — GUI calls core services, no business logic; §III — async via `@asyncSlot()`
  - **Details**: Replace current `_on_run_click()` with state machine:
    ```
    Phase 1 (first click — _awaiting_selection is False):
      1. Validate library path (existing code)
      2. Lock UI (existing code)
      3. Emit SCANNING progress
      4. scan_output = await self.pipeline_runner.library_scanner.scan(Path(library_path))
      5. If scan_output.show_tree is not empty:
         - self.selection_tree.populate(scan_output.show_tree)
         - self.selection_tree.setVisible(True)
         - self._pending_scan_output = scan_output
         - self._awaiting_selection = True
         - self.run_button.setEnabled(True)  # re-enable for second click
         - self.run_button.setText("Run Selected")
         - Unlock library_picker? No — keep locked
         - RETURN (wait for second click)
      6. If show_tree empty: proceed directly (no selection step)

    Phase 2 (second click — _awaiting_selection is True):
      1. self._awaiting_selection = False
      2. selected = self.selection_tree.get_selected_paths()
      3. self.selection_tree.setVisible(False)
      4. self.run_button.setText("Run Pipeline")
      5. Create PipelineConfig with selected_paths=frozenset(selected) if selected else None
      6. Continue with existing pipeline run logic
    ```
    - **Important**: `frozenset(selected)` — convert `set[Path]` from widget to `frozenset` for PipelineConfig

- [x] T028 [US-B1] Wire export log signal from ActivityFeed to handler in `src/gui/main_window.py`
  - **File**: `src/gui/main_window.py`
  - **depends**: T024 (ActivityFeed has signal), T015 (export function exists), T026 (log_bridge stored)
  - **Constitution**: §III — `asyncio.to_thread()` for file I/O via export function
  - **Details**:
    1. In `__init__()`: `self.activity_feed.export_requested.connect(self._on_export_log)`
    2. Add method:
       ```python
       @asyncSlot()
       async def _on_export_log(self) -> None:
           from PySide6.QtWidgets import QFileDialog
           from datetime import date

           default_name = f"anime_studio_log_{date.today().isoformat()}.txt"
           path, _ = QFileDialog.getSaveFileName(
               self, "Export Session Log", default_name, "Text Files (*.txt)"
           )
           if not path:
               return  # User cancelled

           entries = self._log_bridge.get_session_entries()
           try:
               from src.gui.log_bridge import export_session_log
               await export_session_log(entries, Path(path))
               self.signal_bridge.log_received.emit({
                   "event": f"Log exported to {path}",
                   "level": "info",
                   "timestamp": "",
               })
           except Exception as e:
               self.signal_bridge.log_received.emit({
                   "event": f"Log export failed: {e}",
                   "level": "error",
                   "timestamp": "",
               })
       ```

- [x] T029 Update `MainWindow.__init__()` signature to accept and store `log_bridge` reference in `src/gui/main_window.py`
  - **File**: `src/gui/main_window.py` (line 34-41)
  - **depends**: T026
  - **Details**: `self._log_bridge` already receives `log_bridge` as parameter. Verify it is stored as instance attribute. Current code passes `log_bridge` but only uses it for signal connection. Add `self._log_bridge = log_bridge` if not already stored.

- [x] T030 Update `bootstrap.py` to pass `log_bridge` properly and verify no wiring changes needed in `src/gui/bootstrap.py`
  - **File**: `src/gui/bootstrap.py`
  - **depends**: T029
  - **Details**: `bootstrap_app()` already passes `log_bridge=log_bridge` to `MainWindow()`. Verify no changes needed. If `MainWindow.__init__` signature changed, update call accordingly.

**Checkpoint**: `uv run pytest tests/unit/ -v` — ALL tests pass (231 existing + ~25 new ≈ 256 total).

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, cleanup, edge case handling.

- [x] T031 Handle edge case: zero shows found — show placeholder text in `SelectionTreeWidget` in `src/gui/widgets/selection_tree.py`
  - **File**: `src/gui/widgets/selection_tree.py`
  - **depends**: T019
  - **Details**: In `populate()`, if `show_tree` is empty, add a disabled placeholder item: `QTreeWidgetItem(self.tree, ["No shows found", ""])`. Disable checkbox on it.

- [x] T032 Handle edge case: shows with zero episodes — display but unchecked by default in `src/gui/widgets/selection_tree.py`
  - **File**: `src/gui/widgets/selection_tree.py`
  - **depends**: T019
  - **Details**: In `populate()`, if `total_eps == 0` for a show, set `setCheckState(0, Qt.CheckState.Unchecked)` instead of Checked.

- [x] T033 Run full regression test suite
  - **Command**: `uv run pytest tests/unit/ -v`
  - **depends**: T001-T030
  - **Expected**: 250+ tests, 100% pass

- [x] T034 Run ruff linting and formatting checks
  - **Commands**: `uv run ruff check .` then `uv run ruff format --check .`
  - **depends**: T033
  - **Expected**: Zero warnings, zero diffs

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Bug Fix)        → No dependencies — START HERE
Phase 2 (Models)         → No dependencies (parallel with Phase 1)
Phase 3 (Scanner+Log)    → Depends on Phase 2 completion
Phase 4 (Runner+Export)  → Depends on Phase 2 (T006) and Phase 3 Track B (T011)
Phase 5 (Tree Widget)    → Depends on Phase 2 (T004)
Phase 6 (Export Button)  → Depends on Phase 4 Track B (T015)
Phase 7 (MainWindow)     → Depends on Phases 3, 4, 5, 6 ALL complete
Phase 8 (Polish)         → Depends on Phase 7
```

### Parallel Opportunities

| Parallel Group | Tasks | Condition |
|---|---|---|
| **Group 1** | T001-T002 ∥ T003-T007 | Independent — bug fix and models |
| **Group 2** | T008-T010 ∥ T011 | Scanner tree ∥ Log buffer (different files) |
| **Group 3** | T012-T013 ∥ T014-T017 | Runner filter ∥ Log format+export (different files) |
| **Group 4** | T018-T023 ∥ T024-T025 | Tree widget ∥ Export button (different files) |

### Critical Path

```
T003 → T004 → T005 → T008 → T009 → T018 → T019 → T020 → T026 → T027 → T033
```

This is the longest chain (11 tasks). All other tracks merge into T026 (MainWindow integration).

---

## Parallel Example: Wave 2

```bash
# Track A (scanner tree) and Track B (log buffer) run in parallel:

# Track A:
Task: "T008 Add _build_show_tree() to LibraryScanner in src/core/library_scanner.py"
Task: "T009 Wire _build_show_tree() into scan() in src/core/library_scanner.py"
Task: "T010 Tests for show_tree in tests/unit/core/test_library_scanner.py"

# Track B (parallel — different file):
Task: "T011 Add session buffer to GuiLogBridge in src/gui/log_bridge.py"
```

---

## Implementation Strategy

### MVP First (Scan Bug Fix + Selective Run Only)

1. Complete Phase 1: Bug fix (T001-T002) — 5 min
2. Complete Phase 2: Models (T003-T007) — 15 min
3. Complete Phase 3 Track A: Scanner tree (T008-T010) — 20 min
4. Complete Phase 4 Track A: Runner filter (T012-T013) — 15 min
5. Complete Phase 5: SelectionTreeWidget (T018-T023) — 45 min
6. Complete Phase 7 partial: MainWindow tree integration (T026-T027) — 20 min
7. **STOP and VALIDATE**: Test selective run end-to-end
8. Then add Export Log (T011, T014-T017, T024-T025, T028-T030) — 30 min

### Full Delivery

1. Phases 1-8 sequentially with parallel opportunities → ~2.5 hours estimated
2. 34 tasks total, ~25 new tests
3. Final test count: 256+ (231 existing + 25 new)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to spec user story for traceability
- **CRITICAL**: `Qt.ItemFlag.ItemIsAutoTristate` (NOT `ItemIsUserTristate`) — auto-propagates parent↔child checkboxes
- **CRITICAL**: `frozenset[Path]` in PipelineConfig (frozen Pydantic model requires immutable types)
- **CRITICAL**: `_amux_` pattern: `re.compile(r'^_amux_.*\.tmp\.\w+$')` at module level
- Log buffer cap: 10000 entries (session memory limit)
- Export format: `[HH:MM:SS] [LEVEL] event | key=value key=value`
- Commit after each phase checkpoint
- Run `uv run pytest tests/unit/ -v` after every phase
