# Tasks: PySide6 Dashboard

**Input**: Design documents from `/specs/006-pyside-dashboard/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec. Test tasks omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Remove Flet, install PySide6 stack, establish new entry point and theme

- [ ] T001 Add PySide6, qasync, qdarktheme to pyproject.toml dependencies and remove flet
- [ ] T002 Create dark theme module with qdarktheme + Fusion fallback in src/gui/theme.py
- [ ] T003 Create SignalBridge QObject with typed signals in src/gui/signals.py
- [ ] T004 Rewrite entry point for PySide6 + qasync event loop in src/__main__.py
- [ ] T005 Delete obsolete Flet files: src/gui/app.py, src/gui/screens/dashboard.py, src/gui/styles/ directory
- [ ] T006 [P] Update src/gui/__init__.py exports for new module structure

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Rewrite composition root (bootstrap) and core widget base classes that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T007 Rewrite src/gui/bootstrap.py to wire QApplication → PySide6 services → MainWindow (replace all Flet page references with Qt equivalents, preserve PipelineRunner/FontResolver/HunterRegistry wiring)
- [ ] T008 Create QMainWindow shell in src/gui/main_window.py with title, sizing (1100×800, min 800×600), central widget layout (QSplitter or QVBoxLayout with 4 panels), close event override with pipeline-running confirmation dialog
- [ ] T009 Integrate log_bridge.py queue drain into SignalBridge via QTimer(100ms) poll loop in src/gui/main_window.py (connect SignalBridge.log_received to activity feed slot)
- [ ] T010 [P] Rewrite src/gui/widgets/error_dialog.py to use QMessageBox (information/warning/critical) instead of Flet SnackBar/AlertDialog
- [ ] T011 Update src/gui/messages.py ErrorInfo.is_critical docstring from "AlertDialog/SnackBar" to "QMessageBox.critical/QMessageBox.information"

**Checkpoint**: Foundation ready — PySide6 app launches with dark theme, empty panels, and signal bridge wired

---

## Phase 3: User Story 1 - Launch & Select Library (Priority: P1) 🎯 MVP

**Goal**: User launches app → dark-themed window appears → clicks "Select Library" → native file dialog → path persisted

**Independent Test**: Launch app, select folder, restart, verify path restored

### Implementation for User Story 1

- [ ] T012 [US1] Create LibraryPickerWidget (QWidget with QLineEdit read-only + QPushButton "Select Library") in src/gui/widgets/library_picker.py
- [ ] T013 [US1] Implement QFileDialog.getExistingDirectory call in LibraryPickerWidget.browse_clicked slot in src/gui/widgets/library_picker.py
- [ ] T014 [US1] Add library_path field to AppConfig in src/config.py and implement save_to_toml() method for path persistence
- [ ] T015 [US1] Wire LibraryPickerWidget into MainWindow config panel, connect library_selected signal to enable "Run Pipeline" button in src/gui/main_window.py
- [ ] T016 [US1] Load persisted library_path from config.toml on startup and pre-populate LibraryPickerWidget in src/gui/bootstrap.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Real-Time Activity Feed (Priority: P2)

**Goal**: Curated INFO+ log events appear in scrolling feed during pipeline runs, with auto-scroll and manual scroll-pause

**Independent Test**: Start pipeline, verify events appear <500ms, verify scroll behavior

### Implementation for User Story 2

- [ ] T017 [US2] Rewrite ActivityFeedWidget as QPlainTextEdit subclass with setReadOnly(True), setMaximumBlockCount(5000), setUndoRedoEnabled(False) in src/gui/widgets/activity_feed.py
- [ ] T018 [US2] Implement batched append via QTimer(100ms) with internal buffer list, format entries as "[LEVEL] timestamp - message" in src/gui/widgets/activity_feed.py
- [ ] T019 [US2] Implement auto-scroll with pause-on-user-scroll: check verticalScrollBar().value() >= maximum() - 4 before append, only scroll to bottom if user was at bottom in src/gui/widgets/activity_feed.py
- [ ] T020 [US2] Connect SignalBridge.log_received signal to ActivityFeedWidget.add_entry slot in src/gui/main_window.py
- [ ] T021 [US2] Wire ActivityFeedWidget into MainWindow left panel in src/gui/main_window.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Progress Tracking (Priority: P3)

**Goal**: QProgressBar shows operation progress (indeterminate for scanning, determinate for muxing), with visual states for complete/error

**Independent Test**: Trigger pipeline, verify progress bar appears, updates, shows green/red on complete/error

### Implementation for User Story 3

- [ ] T022 [US3] Rewrite ProgressPanelWidget with QProgressBar + QLabel for status text in src/gui/widgets/progress_panel.py
- [ ] T023 [US3] Implement update_state(ProgressState) method: IDLE=hidden, SCANNING=indeterminate (setRange(0,0)), MUXING=determinate (0-100%), COMPLETE=100% green stylesheet, ERROR=red stylesheet in src/gui/widgets/progress_panel.py
- [ ] T024 [US3] Connect SignalBridge.progress_updated signal to ProgressPanelWidget.update_state slot in src/gui/main_window.py
- [ ] T025 [US3] Wire ProgressPanelWidget into MainWindow right-top panel in src/gui/main_window.py

**Checkpoint**: All three user stories should now be independently functional

---

## Phase 6: User Story 4 - Results Table (Priority: P4)

**Goal**: Sortable table showing per-episode pipeline results with copy support

**Independent Test**: Complete pipeline run, verify table populates, columns sort, cells copyable

### Implementation for User Story 4

- [ ] T026 [US4] Create ResultsModel(QAbstractTableModel) with columns [Name, Status, Fonts Found, Fonts Missing, Error] and set_results(list) method in src/gui/widgets/results_table.py
- [ ] T027 [US4] Create ResultsTableWidget with QTableView + QSortFilterProxyModel, setSortingEnabled(True), setSelectionBehavior(SelectRows) in src/gui/widgets/results_table.py
- [ ] T028 [US4] Implement populate(PipelineRunResult) method that maps EpisodeResult list to model rows, with status emoji (✓/⚠/✗) and error tooltips via Qt.ToolTipRole in src/gui/widgets/results_table.py
- [ ] T029 [US4] Implement context menu (right-click → "Copy Cell", "Copy Row") via customContextMenuRequested signal + QMenu in src/gui/widgets/results_table.py
- [ ] T030 [US4] Implement Ctrl+C keyboard shortcut for selected cells via keyPressEvent override in src/gui/widgets/results_table.py
- [ ] T031 [US4] Connect SignalBridge.pipeline_finished signal to ResultsTableWidget.populate slot in src/gui/main_window.py
- [ ] T032 [US4] Wire ResultsTableWidget into MainWindow right-bottom panel in src/gui/main_window.py

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: Pipeline Integration & Run Button

**Purpose**: Wire the "Run Pipeline" button to PipelineRunner via async coroutine

- [ ] T033 Implement _on_run_click as @asyncSlot() that calls PipelineRunner.run(), emits progress/finished/error signals via SignalBridge, and manages button enable/disable state in src/gui/main_window.py
- [ ] T034 Implement progress callback bridging: connect PipelineRunner progress events → SignalBridge.progress_updated in src/gui/main_window.py
- [ ] T035 Implement pipeline error handling: catch exceptions → SignalBridge.pipeline_error → QMessageBox.critical in src/gui/main_window.py
- [ ] T036 Implement pipeline result mapping: PipelineReport → PipelineRunResult → SignalBridge.pipeline_finished in src/gui/main_window.py (reuse map_pipeline_report from bootstrap.py)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, accessibility, and cleanup

- [ ] T037 [P] Implement close-during-pipeline confirmation dialog (QMessageBox.question) with graceful subprocess cancellation in src/gui/main_window.py closeEvent
- [ ] T038 [P] Implement invalid library path detection: show warning banner when selected path is inaccessible, disable Run button in src/gui/main_window.py
- [ ] T039 [P] Update src/gui/widgets/__init__.py to export new widget classes (LibraryPickerWidget, ActivityFeedWidget, ProgressPanelWidget, ResultsTableWidget)
- [ ] T040 [P] Remove all remaining Flet imports from src/gui/ directory — grep for "import flet" and "from flet" and delete/replace
- [ ] T041 Run quickstart.md validation: launch app, execute all 7 smoke test scenarios
- [ ] T042 Code cleanup: remove src/gui/screens/ directory entirely, remove src/gui/styles/ directory entirely

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (Phase 3): Independent, can start first
  - US2 (Phase 4): Independent of US1 (signal bridge wired in Phase 2)
  - US3 (Phase 5): Independent of US1/US2
  - US4 (Phase 6): Independent of US1/US2/US3
- **Pipeline Integration (Phase 7)**: Depends on US1 (library selection), US2 (feed), US3 (progress), US4 (results)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - No dependencies on US1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - No dependencies on US1/US2
- **User Story 4 (P4)**: Can start after Foundational (Phase 2) - No dependencies on US1/US2/US3

### Within Each User Story

- Widget implementation before wiring into MainWindow
- Signal connections after widget exists
- Integration after all widgets wired

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel
- All Polish tasks marked [P] can run in parallel

---

## Parallel Example: User Story 2

```bash
# These can run in parallel (different files, no deps):
Task: "Rewrite ActivityFeedWidget as QPlainTextEdit in src/gui/widgets/activity_feed.py"

# These must wait for widget to exist:
Task: "Connect SignalBridge.log_received to ActivityFeedWidget.add_entry in src/gui/main_window.py"
Task: "Wire ActivityFeedWidget into MainWindow left panel in src/gui/main_window.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (remove Flet, add PySide6)
2. Complete Phase 2: Foundational (bootstrap, main_window shell, signal bridge)
3. Complete Phase 3: User Story 1 (library picker)
4. **STOP and VALIDATE**: Launch app, select folder, verify persistence
5. Ship MVP if ready

### Incremental Delivery

1. Complete Setup + Foundational → Dark-themed window launches
2. Add User Story 1 → Library selection works → MVP!
3. Add User Story 2 → Activity feed streams events
4. Add User Story 3 → Progress bars track operations
5. Add User Story 4 → Results table displays outcomes
6. Pipeline Integration → Full end-to-end pipeline via GUI
7. Polish → Edge cases, cleanup

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
