# Tasks: GUI Dashboard

**Input**: Design documents from `/specs/005-gui-dashboard/`

**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/gui_contract.md ✅, research.md ✅, quickstart.md ✅

**Tests**: Included — spec.md references unit tests (test_messages, test_log_bridge, test_boundary, test_activity_feed, test_progress_panel, test_results_table, test_app) and plan.md lists tests/ structure.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `src/gui/` package tree and test scaffold. Add `flet` dependency.

- [x] T001 Create `src/gui/` package directories: `src/gui/__init__.py`, `src/gui/screens/__init__.py`, `src/gui/widgets/__init__.py`, `src/gui/styles/` (no __init__ needed — single module)
- [x] T002 [P] Create `tests/unit/gui/` package with `tests/unit/gui/__init__.py`
- [x] T003 [P] Add `flet` dependency to `pyproject.toml` under project dependencies

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core message types, theme, log bridge, and bootstrap that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [P] Implement GUI message dataclasses (`ActivityEntry`, `ProgressState`, `ProgressPhase`, `EpisodeResult`, `EpisodeStatus`, `PipelineRunResult`, `ErrorInfo`) in `src/gui/messages.py` per data-model.md
- [x] T005 [P] Implement Material Design theme config (color palette, typography, spacing constants) in `src/gui/styles/theme.py`
- [x] T006 Implement `GuiLogBridge` structlog processor with `asyncio.Queue` capture of INFO+ events in `src/gui/log_bridge.py` per contracts/gui_contract.md and research.md R2
- [x] T007 Implement composition root `create_app()` in `src/gui/bootstrap.py` — wire adapters → PipelineRunner → log bridge → DashboardView per contracts/gui_contract.md bootstrap contract. Include `PipelineReport` → `PipelineRunResult` mapper function.
- [x] T008 [P] Write unit tests for message dataclass construction and enum values in `tests/unit/gui/test_messages.py`
- [x] T009 [P] Write unit tests for `GuiLogBridge` processor (INFO+ capture, DEBUG filtering, pass-through) in `tests/unit/gui/test_log_bridge.py`
- [x] T010 Write import boundary compliance test using `ast.parse` to enforce boundary rules table from contracts/gui_contract.md in `tests/unit/gui/test_boundary.py`

**Checkpoint**: Foundation ready — all message types, log bridge, theme, bootstrap wired. User story implementation can begin.

---

## Phase 3: User Story 1 — Launch Dashboard & Library Selection (Priority: P1) 🎯 MVP

**Goal**: Operator launches app → sees Material Design dashboard with directory picker and "Run Pipeline" button → selects library folder → initiates pipeline run.

**Independent Test**: Launch app, verify dashboard renders <2s, select folder via FilePicker, press "Run Pipeline". Delivers usable entry point.

### Implementation for User Story 1

- [x] T011 [US1] Implement `DashboardView` screen in `src/gui/screens/dashboard.py` — compose header, `FilePicker` directory selector, "Dry Run" checkbox (visible but wired in US6), "Run Pipeline" button (disabled until path selected), and panel placeholders for activity feed / progress / results
- [x] T012 [US1] Implement Flet app entry `main(page)` in `src/gui/app.py` — call `create_app()` from bootstrap, configure page title/theme/window size per research.md R1
- [x] T013 [US1] Update `src/__main__.py` to launch Flet GUI via `ft.app(target=main)` instead of previous entry point
- [x] T014 [P] [US1] Write app lifecycle tests (main callable, page configuration) in `tests/unit/gui/test_app.py`

**Checkpoint**: Dashboard launches, operator can pick a directory and press "Run Pipeline". Activity feed / progress / results panels are placeholder containers.

---

## Phase 4: User Story 2 — Real-Time Activity Feed (Priority: P1)

**Goal**: During pipeline run, curated INFO+ log entries appear in a live, auto-scrolling feed panel with color-coded severity. Updates throttled to ~10/sec.

**Independent Test**: Run pipeline, verify INFO-level events appear within 500ms, WARNING/ERROR visually distinguished, UI responsive under burst.

### Implementation for User Story 2

- [ ] T015 [US2] Implement `ActivityFeed` widget in `src/gui/widgets/activity_feed.py` — `ListView` displaying `ActivityEntry` rows with timestamp, severity icon/color, category, message. Auto-scroll to bottom; pause auto-scroll on manual scroll-up per spec.md US2 acceptance criteria
- [ ] T016 [US2] Implement throttled queue consumer coroutine in `ActivityFeed` — 100ms batch drain loop per research.md R8 (`THROTTLE_INTERVAL_MS = 100`). Converts raw event dicts from `asyncio.Queue` → `ActivityEntry` → formatted `ListTile` controls. Single `update()` per batch.
- [ ] T017 [US2] Wire `ActivityFeed` into `DashboardView` in `src/gui/screens/dashboard.py` — pass `log_queue` from bootstrap, start consumer coroutine on pipeline run
- [ ] T018 [P] [US2] Write unit tests for `ActivityFeed` entry formatting and throttle logic in `tests/unit/gui/test_activity_feed.py`

**Checkpoint**: Activity feed shows live log entries during pipeline run with correct formatting and throttling.

---

## Phase 5: User Story 3 — Progress Tracking (Priority: P1)

**Goal**: Operator sees indeterminate `ProgressRing` during library scan phase, then determinate `ProgressBar` showing N/M episodes during mux phase. Summary shown on completion.

**Independent Test**: Run pipeline on multi-episode library, verify spinner during scan, progress bar advances per episode, 100% + summary on completion.

### Implementation for User Story 3

- [ ] T019 [US3] Implement `ProgressPanel` widget in `src/gui/widgets/progress_panel.py` — render `ProgressRing` (indeterminate) for SCANNING phase, `ProgressBar` (determinate) for MUXING phase, completion summary for COMPLETE phase per research.md R5. Accept `ProgressState` updates.
- [ ] T020 [US3] Implement `ProgressCallback` protocol adapter in `src/gui/bootstrap.py` — translate `on_scan_start/on_scan_complete/on_mux_progress/on_pipeline_complete/on_pipeline_error` callbacks into `ProgressState` mutations and widget updates per contracts/gui_contract.md progress callback contract
- [ ] T021 [US3] Wire `ProgressPanel` into `DashboardView` in `src/gui/screens/dashboard.py` — inject progress callback into pipeline runner invocation
- [ ] T022 [P] [US3] Write unit tests for `ProgressPanel` state transitions (IDLE→SCANNING→MUXING→COMPLETE, any→ERROR) in `tests/unit/gui/test_progress_panel.py`

**Checkpoint**: Progress indicators render correctly for all pipeline phases — spinner, bar with N/M, and final summary.

---

## Phase 6: User Story 4 — Post-Run Results Table (Priority: P2)

**Goal**: After pipeline completion, operator sees sortable `DataTable` with per-episode rows (status icon, name, font count, error summary) plus aggregate stats and report path.

**Independent Test**: Complete pipeline run, verify results table appears with accurate episode data, sort by column works, report path displayed.

### Implementation for User Story 4

- [ ] T023 [US4] Implement `ResultsTable` widget in `src/gui/widgets/results_table.py` — `DataTable` with sortable columns (Episode, Status, Fonts, Errors) per research.md R3. Render `EpisodeResult` rows with status icons (✓/⚠/✗). Show aggregate stats row and report path. Include "Run Again" button.
- [ ] T024 [US4] Wire `ResultsTable` into `DashboardView` in `src/gui/screens/dashboard.py` — populate from `PipelineRunResult` after pipeline completion. Show/hide based on pipeline state.
- [ ] T025 [P] [US4] Write unit tests for `ResultsTable` row rendering and sort logic in `tests/unit/gui/test_results_table.py`

**Checkpoint**: Results table correctly displays all episode outcomes with sorting, font stats, and report path after pipeline run.

---

## Phase 7: User Story 5 — Error Presentation & Notifications (Priority: P2)

**Goal**: Pipeline errors shown as styled widgets — `AlertDialog` modal for critical errors, `SnackBar` dismissible notification for non-critical. Never raw tracebacks.

**Independent Test**: Simulate tool-not-found error → verify modal dialog. Simulate font-match failure → verify dismissible notification. Zero raw tracebacks.

### Implementation for User Story 5

- [ ] T026 [US5] Implement `show_error()` function and error presentation logic in `src/gui/widgets/error_dialog.py` — accept `ErrorInfo`, show `AlertDialog` (modal, with title/message/suggestion/dismiss) when `is_critical=True`, show `SnackBar` when `is_critical=False` per research.md R6 and contracts/gui_contract.md
- [ ] T027 [US5] Wire error presentation into `DashboardView` in `src/gui/screens/dashboard.py` — catch pipeline exceptions at boundary, convert to `ErrorInfo`, invoke `show_error()`. Integrate error count into results table.
- [ ] T028 [US5] Add error event handling to `src/gui/bootstrap.py` — implement `on_pipeline_error` callback to convert exceptions → `ErrorInfo` and trigger error dialog

**Checkpoint**: All pipeline errors render as styled widgets. Critical → modal dialog. Non-critical → dismissible SnackBar. Zero raw tracebacks anywhere.

---

## Phase 8: User Story 6 — Dry-Run Mode Toggle (Priority: P3)

**Goal**: Operator toggles "Dry Run" checkbox on dashboard → pipeline simulates without modifying files → activity feed entries tagged "[DRY RUN]".

**Independent Test**: Enable dry-run, run pipeline, verify zero file modifications, activity feed shows "[DRY RUN]" banner.

### Implementation for User Story 6

- [ ] T029 [US6] Wire dry-run checkbox state in `src/gui/screens/dashboard.py` to `PipelineConfig.dry_run` parameter when constructing config for `PipelineRunner.run()` call
- [ ] T030 [US6] Add "[DRY RUN]" banner/label to dashboard header and activity feed entries in `src/gui/screens/dashboard.py` when dry-run mode is active
- [ ] T031 [US6] Update `ActivityFeed` in `src/gui/widgets/activity_feed.py` to visually tag entries with "[DRY RUN]" prefix when dry-run mode is active

**Checkpoint**: Dry-run toggle fully wired. Pipeline simulates without file modifications. All UI surfaces reflect dry-run state.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, and validation across all stories

- [ ] T032 [P] Update `README.md` or project docs with GUI launch instructions per quickstart.md
- [ ] T033 [P] Add docstrings and type hints to all `src/gui/` modules
- [ ] T034 Run `ruff check` and `ruff format` on all `src/gui/` and `tests/unit/gui/` files
- [ ] T035 Verify import boundary compliance by running `pytest tests/unit/gui/test_boundary.py -v`
- [ ] T036 Run full test suite `pytest tests/unit/gui/ -v` and fix any failures
- [ ] T037 Validate quickstart.md workflow end-to-end: install deps, launch GUI, pick directory, run pipeline, verify all panels

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (Phase 2)
- **US2 (Phase 4)**: Depends on Foundational (Phase 2) + US1 (needs DashboardView container)
- **US3 (Phase 5)**: Depends on Foundational (Phase 2) + US1 (needs DashboardView container)
- **US4 (Phase 6)**: Depends on Foundational (Phase 2) + US1 (needs DashboardView container)
- **US5 (Phase 7)**: Depends on Foundational (Phase 2) + US1 (needs DashboardView container)
- **US6 (Phase 8)**: Depends on US1 (wires existing checkbox)
- **Polish (Phase 9)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: After Phase 2. No other story dependencies. **MVP scope.**
- **US2 (P1)**: After Phase 2 + US1. Independent of US3–US6.
- **US3 (P1)**: After Phase 2 + US1. Independent of US2, US4–US6.
- **US4 (P2)**: After Phase 2 + US1. Independent of US2, US3, US5, US6.
- **US5 (P2)**: After Phase 2 + US1. Independent of US2–US4, US6.
- **US6 (P3)**: After US1. Independent of US2–US5.

### Within Each User Story

- Widget implementation first
- Integration/wiring into DashboardView second
- Tests can be written in parallel with implementation ([P] marked)

### Parallel Opportunities

- **Phase 1**: T001 ‖ T002 ‖ T003 (all independent)
- **Phase 2**: T004 ‖ T005 (independent); T008 ‖ T009 ‖ T010 (test files independent)
- **After US1**: US2 ‖ US3 ‖ US4 ‖ US5 can proceed in parallel (different widget files)
- **Within stories**: Test tasks marked [P] can run alongside implementation

---

## Parallel Example: After Phase 2

```text
# All these stories touch different files — can run simultaneously:
Stream A (US2): T015 → T016 → T017 + T018[P]  (activity_feed.py)
Stream B (US3): T019 → T020 → T021 + T022[P]  (progress_panel.py)
Stream C (US4): T023 → T024 + T025[P]          (results_table.py)
Stream D (US5): T026 → T027 → T028             (error_dialog.py)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T010)
3. Complete Phase 3: US1 — Dashboard & Library Selection (T011–T014)
4. **STOP and VALIDATE**: Launch app, pick directory, press "Run Pipeline"
5. Deploy/demo if ready — functional entry point delivered

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 → Test independently → **MVP!** (launchable dashboard)
3. US2 → Activity feed live → real-time feedback during runs
4. US3 → Progress tracking → operator sees scan/mux progress
5. US4 → Results table → post-run episode summary
6. US5 → Error presentation → polished error handling
7. US6 → Dry-run toggle → full feature parity with CLI
8. Polish → docs, lint, validation

### Parallel Team Strategy

With multiple developers after Phase 2:
- Developer A: US1 (dashboard core) → US6 (dry-run wiring)
- Developer B: US2 (activity feed) → US4 (results table)
- Developer C: US3 (progress panel) → US5 (error dialog)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story independently completable and testable after US1 provides the dashboard container
- All GUI modules follow strict import boundaries per contracts/gui_contract.md
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
