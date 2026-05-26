# Tasks: TUI Dashboard

**Input**: Design documents from `specs/005-tui-dashboard/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/tui_contract.md

**Tests**: Included — spec mandates Textual Pilot tests and boundary compliance tests.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create TUI package structure and foundational files

- [x] T001 Create TUI package directories: `src/tui/`, `src/tui/screens/`, `src/tui/widgets/`, `src/tui/styles/`
- [x] T002 [P] Create `src/tui/__init__.py` with empty package init
- [x] T003 [P] Create `src/tui/screens/__init__.py` with empty package init
- [x] T004 [P] Create `src/tui/widgets/__init__.py` with empty package init
- [x] T005 Create `tests/unit/tui/__init__.py` test package init

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Define Textual Message subclasses (`LogEntry`, `ProgressUpdate`, `PipelineStarted`, `PipelineCompleted`, `PipelineError`) in `src/tui/messages.py` — all as `textual.message.Message` subclasses with typed fields per data-model.md
- [x] T007 Implement structlog→Textual message bridge processor in `src/tui/log_bridge.py` — a structlog processor function that accepts an `App` reference, filters INFO+ events, and posts `LogEntry` messages; includes buffer/flush for throttling (max 10/sec via timer)
- [x] T008 Create Textual CSS stylesheet in `src/tui/styles/dashboard.tcss` — define layout regions (header, path-input, controls, activity-feed, progress-panel, results-panel), color scheme using Textual semantic colors ($primary, $success, $warning, $error), minimum 80x24 layout support. **CONSTRAINT**: ALL sizing MUST use relative units (`1fr`, `%`, `auto`) exclusively — hardcoded pixel/cell dimensions (e.g., `width: 40;`, `height: 10;`) are FORBIDDEN. This ensures graceful reflow under aggressive terminal resizing.
- [x] T009 Implement `src/tui/bootstrap.py` — factory function `create_app()` that imports adapters, constructs `AppConfig` via `AppConfig.load_from_toml()` (resolves `%APPDATA%\AnimeStudio\config.toml` on Windows, `~/.config/AnimeStudio/config.toml` on Linux/macOS), constructs `ToolRegistry`, `SubprocessAdapter`, `FilesystemAdapter`, `FontResolver`, `PipelineRunner`, installs the log bridge processor, and returns a configured `AnimeStudioApp` instance. **CONSTRAINT**: The loaded `config.proxy` MUST be passed to any `httpx.AsyncClient` construction within adapters, and `config.max_concurrent_disk_io` MUST be used to create the shared `asyncio.Semaphore` injected into adapters via the DI container — never hardcoded.
- [x] T010 [P] Write unit test `tests/unit/tui/test_messages.py` — verify all Message subclasses construct correctly with expected fields and can be posted/received

**Checkpoint**: Foundation ready — message types, log bridge, CSS, and bootstrap wired. User story implementation can now begin.

---

## Phase 3: User Story 1 — Launch Dashboard & Library Selection (Priority: P1) 🎯 MVP

**Goal**: Operator launches app, sees dashboard with path input and "Run Pipeline" button, initiates pipeline run

**Independent Test**: Launch app via Pilot, verify dashboard renders, enter path, press button, verify pipeline worker starts

### Tests for User Story 1

- [x] T011 [P] [US1] Write Pilot test `tests/unit/tui/test_app.py` — test app launches, dashboard screen displays within timeout, header/input/button visible
- [x] T012 [P] [US1] Write Pilot test in `tests/unit/tui/test_app.py` — test invalid path disables button, valid path enables button

### Implementation for User Story 1

- [x] T013 [US1] Implement `AnimeStudioApp(App)` in `src/tui/app.py` — Textual App subclass with `CSS_PATH = "styles/dashboard.tcss"`, `BINDINGS` for quit (q), dark mode toggle (d); `compose()` yields `DashboardScreen`; holds `PipelineRunner` reference from constructor injection
- [x] T014 [US1] Implement `DashboardScreen(Screen)` in `src/tui/screens/dashboard.py` — compose: Header, Input (id="library-path", placeholder="Enter library path..."), Checkbox (id="dry-run", label="Dry Run"), Button (id="run-pipeline", label="Run Pipeline", variant="primary", disabled=True), containers for ActivityFeed and ProgressPanel (initially hidden), ResultsSummary (initially hidden)
- [x] T015 [US1] Add input validation in `src/tui/screens/dashboard.py` — watch Input.Changed, validate path is non-empty string, enable/disable Button accordingly; on Button.Pressed, construct `PipelineConfig` from inputs, call `self.app.run_worker(self._run_pipeline(config), exclusive=True)`; disable button during run (FR-012)
- [x] T016 [US1] Implement pipeline worker method `_run_pipeline()` in `src/tui/screens/dashboard.py` — post `PipelineStarted` message, call `self.app.pipeline_runner.run(config)`, post `PipelineCompleted(report)` on success, catch `AnimeStudioError` and post `PipelineError`, re-enable button on completion. **CONSTRAINT**: MUST handle Python 3.11+ `ExceptionGroup` — if an `ExceptionGroup` is caught, unwrap it via `eg.exceptions` and extract any `AnimeStudioError` subclass instances from the group before posting individual `PipelineError` messages for each; non-domain exceptions within the group should be logged at ERROR level and posted as a generic fatal `PipelineError`.
- [x] T017 [US1] Update `src/__main__.py` — import `create_app` from `src.tui.bootstrap`, call `app = create_app()`, call `app.run()`

**Checkpoint**: App launches, dashboard renders, operator can enter path and start pipeline. Minimum viable TUI.

---

## Phase 4: User Story 2 — Real-Time Activity Feed (Priority: P1)

**Goal**: Operator sees live curated log entries during pipeline execution

**Independent Test**: Run pipeline via Pilot, verify LogEntry messages appear as formatted entries in ActivityFeed widget within 500ms

### Tests for User Story 2

- [x] T018 [P] [US2] Write Pilot test `tests/unit/tui/test_activity_feed.py` — test ActivityFeed widget appends formatted entries when LogEntry messages posted, test auto-scroll behavior, test level-based coloring (INFO=default, WARNING=yellow, ERROR=red)
- [x] T019 [P] [US2] Write unit test `tests/unit/tui/test_log_bridge.py` — test structlog processor creates LogEntry messages for INFO+ events, ignores DEBUG, test throttle buffer (11th message within 100ms is buffered not dropped)

### Implementation for User Story 2

- [x] T020 [US2] Implement `ActivityFeed(Widget)` in `src/tui/widgets/activity_feed.py` — wraps Textual `RichLog` with `auto_scroll=True`; handles `LogEntry` messages by formatting `[timestamp] [level_icon] event_text` and writing to log; uses level-based Rich markup for color (INFO=default, WARNING=$warning, ERROR=$error); implements manual scroll detection to pause auto-scroll
- [x] T021 [US2] Wire ActivityFeed into DashboardScreen in `src/tui/screens/dashboard.py` — add ActivityFeed widget to compose(), make visible when PipelineStarted message received, mount log bridge flush timer (100ms interval via `set_interval`) that drains buffered messages
- [x] T022 [US2] Add CSS rules for ActivityFeed in `src/tui/styles/dashboard.tcss` — height: 1fr for feed panel, scrollbar styling, level-based color classes

**Checkpoint**: Activity feed shows real-time log entries during pipeline run. Throttled rendering prevents UI stutter.

---

## Phase 5: User Story 3 — Progress Tracking (Priority: P1)

**Goal**: Operator sees spinner for library scan and determinate progress bar for mux jobs

**Independent Test**: Post ProgressUpdate messages via Pilot, verify spinner/progress bar updates correctly

### Tests for User Story 3

- [x] T023 [P] [US3] Write Pilot test `tests/unit/tui/test_progress_panel.py` — test indeterminate mode (spinner visible when stage="scan"), test determinate mode (progress bar advances on stage="mux" with current/total), test completion state (100% label)

### Implementation for User Story 3

- [x] T024 [US3] Implement `ProgressPanel(Widget)` in `src/tui/widgets/progress_panel.py` — composes: Label (id="progress-stage"), ProgressBar (id="progress-bar"), Label (id="progress-detail"); handles ProgressUpdate messages: if indeterminate → show LoadingIndicator + label, if determinate → update ProgressBar.progress and detail label (e.g., "Muxing: 3/12 episodes"); on stage="done" → show completion summary with ✓ icon
- [x] T025 [US3] Add PipelineRunner progress event emission in `src/core/pipeline_runner.py` — add structlog.info() calls with `progress_current` and `progress_total` context keys at: scan start (indeterminate), scan complete (total=N), per-episode mux start/complete (current=i, total=N), pipeline complete
- [x] T026 [US3] Update log bridge in `src/tui/log_bridge.py` — detect events with `progress_current`/`progress_total` keys and post `ProgressUpdate` messages instead of `LogEntry`
- [x] T027 [US3] Wire ProgressPanel into DashboardScreen in `src/tui/screens/dashboard.py` — add ProgressPanel to compose(), show on PipelineStarted, hide on PipelineCompleted
- [x] T028 [US3] Add CSS rules for ProgressPanel in `src/tui/styles/dashboard.tcss` — fixed height for panel, progress bar styling, stage label styling

**Checkpoint**: Progress indicators show scan spinner and mux progress bar during pipeline run.

---

## Phase 6: User Story 4 — Pipeline Results Summary (Priority: P2)

**Goal**: Operator sees per-episode status, font stats, and report path after pipeline completes

**Independent Test**: Post PipelineCompleted with mock PipelineReport, verify ResultsSummary renders all fields

### Tests for User Story 4

- [x] T029 [P] [US4] Write Pilot test `tests/unit/tui/test_results_summary.py` — test ResultsSummary displays episode count, per-episode status icons (✓/⚠/✗), font stats, duration, and report path when PipelineCompleted message received

### Implementation for User Story 4

- [x] T030 [US4] Implement `ResultsSummary(Widget)` in `src/tui/widgets/results_summary.py` — handles PipelineCompleted message; composes: Static header ("Pipeline Complete"), DataTable with columns (Episode, Status, Fonts Missing) populated from report.episodes, Label for total_fonts_found and genuine_misses count, Label for duration (formatted from duration_ms), Label for report path, Button (id="run-again", label="Run Again", variant="primary"). **CONSTRAINT**: The report path label MUST display the absolute resolved path to `_AnimeStudio_Report.md` computed as `Path(pipeline_config.library_path).resolve() / "_AnimeStudio_Report.md"` — never a relative or unresolved path.
- [x] T031 [US4] Wire ResultsSummary into DashboardScreen in `src/tui/screens/dashboard.py` — add to compose(), show on PipelineCompleted message, hide on PipelineStarted; handle "Run Again" button → reset state, re-enable path input and run button
- [x] T032 [US4] Add CSS rules for ResultsSummary in `src/tui/styles/dashboard.tcss` — status icon colors, table styling, report path styling

**Checkpoint**: Results summary renders after pipeline completion with actionable information.

---

## Phase 7: User Story 5 — Error Presentation & Notifications (Priority: P2)

**Goal**: Errors shown as styled widgets, never raw tracebacks

**Independent Test**: Post PipelineError messages, verify modal/toast appears with structured content

### Tests for User Story 5

- [x] T033 [P] [US5] Write Pilot test `tests/unit/tui/test_app.py` — test fatal PipelineError shows ErrorModal with dismiss button, test non-fatal error shows toast notification

### Implementation for User Story 5

- [x] T034 [US5] Implement `ErrorModal(ModalScreen)` in `src/tui/widgets/error_modal.py` — compose: Container with Label (error type title), Static (error message), Static (suggestion if available from ToolExecutionError), Button (id="dismiss", label="Dismiss"); dismiss() pops screen
- [x] T035 [US5] Handle PipelineError in DashboardScreen in `src/tui/screens/dashboard.py` — on PipelineError: if fatal → push ErrorModal screen; if non-fatal → call `self.app.notify(str(error), severity="error")`; map error types per contract (ToolNotFoundError → modal with install instructions, others → toast). **CONSTRAINT**: The handler MUST expect that `PipelineError.error` may already be an unwrapped `AnimeStudioError` extracted from an `ExceptionGroup` (see T016). If the error is not a recognized `AnimeStudioError` subclass, present it as a generic fatal modal with the exception message — never silently swallow unknown errors.
- [x] T036 [US5] Add CSS rules for ErrorModal in `src/tui/styles/dashboard.tcss` — modal overlay styling, error icon color, container sizing

**Checkpoint**: All errors presented as styled widgets. Zero raw tracebacks in TUI.

---

## Phase 8: User Story 6 — Dry-Run Mode Toggle (Priority: P3)

**Goal**: Operator toggles dry-run before pipeline run, events tagged with [DRY RUN]

**Independent Test**: Enable dry-run, start pipeline, verify no files modified and feed shows [DRY RUN] tags

### Tests for User Story 6

- [x] T037 [P] [US6] Write Pilot test `tests/unit/tui/test_app.py` — test Checkbox toggle sets dry_run=True in PipelineConfig, test activity feed entries include "[DRY RUN]" prefix when dry_run enabled

### Implementation for User Story 6

- [x] T038 [US6] Wire Checkbox state into PipelineConfig construction in `src/tui/screens/dashboard.py` — read Checkbox value when "Run Pipeline" pressed, pass to `PipelineConfig(dry_run=checkbox.value)`
- [x] T039 [US6] Add dry-run banner in DashboardScreen in `src/tui/screens/dashboard.py` — when pipeline starts with dry_run=True, show a Static label "[DRY RUN] No files will be modified" at top of execution area; prefix ActivityFeed entries with "[DRY RUN]" when in dry-run mode

**Checkpoint**: Dry-run mode fully wired. No filesystem modifications. All events tagged.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Boundary enforcement, final quality, and documentation

- [x] T040 Write hexagonal boundary compliance test `tests/unit/tui/test_boundary.py` — use AST parsing or import inspection to verify `src/tui/` contains ZERO imports from `src/adapters/`, `src/hunters/`, `subprocess`, `httpx`, `os.path`, `shutil`; verify `src/tui/` does not call `open()` directly
- [x] T041 [P] Add keyboard binding help text in `src/tui/app.py` — ensure Footer displays binding hints (q=Quit, d=Dark Mode)
- [x] T042 Run `ruff check src/tui/ tests/unit/tui/` and `ruff format src/tui/ tests/unit/tui/` — fix all lint/format issues
- [x] T043 Run `pytest tests/unit/tui/ -v` — verify all TUI tests pass
- [x] T044 Run quickstart.md smoke tests manually — verify dashboard launch, dry-run, error scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2. MVP entry point.
- **US2 (Phase 4)**: Depends on Phase 2. Can run parallel with US1 (different files) but benefits from US1 being complete (DashboardScreen exists).
- **US3 (Phase 5)**: Depends on Phase 2 + T007 (log bridge). Modifies `pipeline_runner.py` (T025 — the only core change). Can start after Phase 2.
- **US4 (Phase 6)**: Depends on Phase 2 + US1 (DashboardScreen). Independent from US2/US3.
- **US5 (Phase 7)**: Depends on Phase 2 + US1 (DashboardScreen). Independent from US2/US3/US4.
- **US6 (Phase 8)**: Depends on US1 (dashboard + PipelineConfig construction). Light story.
- **Polish (Phase 9)**: Depends on all user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Foundation only — MVP standalone
- **US2 (P1)**: Foundation only — wires into DashboardScreen from US1 but could be stubbed
- **US3 (P1)**: Foundation + T007 (log bridge) + modifies `pipeline_runner.py`
- **US4 (P2)**: Foundation + US1 DashboardScreen
- **US5 (P2)**: Foundation + US1 DashboardScreen
- **US6 (P3)**: US1 DashboardScreen

### Within Each User Story

- Tests written first (where applicable)
- Widget implementation before screen integration
- Screen wiring before CSS styling

### Parallel Opportunities

- T002, T003, T004 can run in parallel (different __init__.py files)
- T011, T012 can run in parallel (different test scenarios)
- T018, T019 can run in parallel (different test files)
- T023 can run parallel with US2 implementation
- T029 can run parallel with US3 implementation
- US4 and US5 can run fully parallel (different widgets, same screen wiring pattern)

---

## Parallel Example: User Story 2

```bash
# Launch tests in parallel:
Task: "Write Pilot test tests/unit/tui/test_activity_feed.py"
Task: "Write unit test tests/unit/tui/test_log_bridge.py"

# Then implement:
Task: "Implement ActivityFeed widget in src/tui/widgets/activity_feed.py"
Task: "Wire ActivityFeed into DashboardScreen"
Task: "Add CSS rules for ActivityFeed"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (5 tasks)
2. Complete Phase 2: Foundational (5 tasks)
3. Complete Phase 3: User Story 1 (7 tasks)
4. **STOP and VALIDATE**: `python -m src` launches dashboard, path input works, pipeline worker starts
5. MVP deliverable

### Incremental Delivery

1. Setup + Foundational → 10 tasks
2. US1 (Dashboard) → Test independently → MVP ✓
3. US2 (Activity Feed) → Live log feedback ✓
4. US3 (Progress Tracking) → Visual progress ✓
5. US4 (Results Summary) → Post-run actionable info ✓
6. US5 (Error Presentation) → Polished error handling ✓
7. US6 (Dry-Run Toggle) → Safety feature ✓
8. Polish → Production-ready ✓

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- T025 is the ONLY task that modifies existing code outside `src/tui/` — adds structlog progress events to `pipeline_runner.py`
- T017 modifies `src/__main__.py` — the entry point update
- All other tasks are new files in `src/tui/` and `tests/unit/tui/`
- Total task count: 44
- Verify tests fail before implementing
- Commit after each task or logical group
