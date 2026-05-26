# Feature Specification: TUI Dashboard

**Feature Branch**: `005-tui-dashboard`

**Created**: 2026-05-26

**Status**: Draft

**Input**: User description: "Phase 4 TUI. Build a robust Textual 1.x interface as pure consumer of PipelineRunner. Dashboard with real-time log/activity feed from structlog INFO+ events. Progress bars/spinners for Library Scanner and concurrent MuxJobs. Strict Hexagonal bounds: TUI does not perform I/O directly."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch Dashboard & Library Selection (Priority: P1)

The operator launches Anime Studio and sees a polished dashboard screen. The dashboard shows a welcome header, a library path selector (text input or directory picker), and a "Run Pipeline" action button. The operator enters or selects a library path and initiates the pipeline run.

**Why this priority**: Without a launchable dashboard with library selection, no other TUI functionality can be demonstrated. This is the entry point for all subsequent user stories.

**Independent Test**: Can be fully tested by launching the app, verifying dashboard renders correctly, entering a path, and pressing "Run Pipeline". Delivers a usable entry point even if progress/logging isn't wired yet.

**Acceptance Scenarios**:

1. **Given** the application is launched, **When** the TUI initializes, **Then** the dashboard screen displays within 2 seconds with a header, library path input, and "Run Pipeline" button.
2. **Given** the dashboard is displayed, **When** the operator enters a valid directory path, **Then** the path input accepts the value and the "Run Pipeline" button becomes active.
3. **Given** the dashboard is displayed, **When** the operator enters an empty or invalid path, **Then** the "Run Pipeline" button remains disabled and a validation message is shown.
4. **Given** a valid path is entered, **When** the operator presses "Run Pipeline", **Then** the TUI transitions to the pipeline execution view, delegating the actual run to `PipelineRunner`.

---

### User Story 2 - Real-Time Activity Feed (Priority: P1)

During a pipeline run, the operator sees a live activity feed panel showing curated, human-readable messages derived from structlog INFO+ events. The feed scrolls automatically but allows the operator to scroll back to review past entries. Each entry includes a timestamp, event category icon/label, and message.

**Why this priority**: Real-time feedback is critical for operator trust and debugging. Without a visible activity feed, the operator has no confirmation that the pipeline is working or insight into what's happening.

**Independent Test**: Can be tested by running a pipeline and verifying that INFO-level structlog events appear in the feed panel in real time with correct timestamps and formatting.

**Acceptance Scenarios**:

1. **Given** a pipeline run is in progress, **When** an INFO-level structlog event is emitted (e.g., "library scan started"), **Then** a formatted entry appears in the activity feed within 500ms.
2. **Given** the activity feed is displaying events, **When** a WARNING or ERROR event is emitted, **Then** the entry is visually distinguished (color/icon) from INFO entries.
3. **Given** the feed has more entries than the visible area, **When** new entries arrive, **Then** the feed auto-scrolls to show the latest entry.
4. **Given** the feed is auto-scrolling, **When** the operator manually scrolls up, **Then** auto-scroll pauses; when the operator scrolls back to the bottom, auto-scroll resumes.

---

### User Story 3 - Progress Tracking for Long-Running Operations (Priority: P1)

The operator sees distinct visual progress indicators for long-running operations: a spinner/indeterminate bar for the Library Scanner, and a determinate progress bar for concurrent MuxJobs (showing N/M completed). Font resolution progress is shown per-episode as a sub-indicator.

**Why this priority**: Without progress indicators, the operator cannot distinguish a slow pipeline from a hung one. Progress bars for mux operations directly address the "12-episode series in <10 minutes" performance visibility goal.

**Independent Test**: Can be tested by running a pipeline on a multi-episode library and verifying progress bars update correctly as episodes complete muxing, and that the scanner shows a spinner while scanning.

**Acceptance Scenarios**:

1. **Given** a pipeline run is initiated, **When** the library scanner begins, **Then** a spinner or indeterminate progress bar is displayed with a "Scanning library..." label.
2. **Given** the library scan completes and mux jobs begin, **When** a mux job finishes, **Then** the progress bar advances (e.g., "Muxing: 3/12 episodes complete").
3. **Given** multiple mux jobs are running concurrently, **When** progress updates are emitted, **Then** the progress bar accurately reflects the total completed vs. total planned.
4. **Given** all mux jobs complete, **When** the pipeline finishes, **Then** the progress bar shows 100% and a summary replaces it (e.g., "✓ 12/12 episodes muxed").

---

### User Story 4 - Pipeline Results Summary (Priority: P2)

After a pipeline run completes, the operator sees a results summary panel showing per-episode status (✓ complete, ⚠ partial, ✗ failed), total fonts found/missing, total duration, and a link/path to the generated `_AnimeStudio_Report.md`.

**Why this priority**: Post-run summary gives the operator actionable information about what succeeded and what needs attention. Less critical than real-time feedback but essential for workflow completion.

**Independent Test**: Can be tested by completing a pipeline run and verifying the summary panel appears with accurate episode counts, font stats, and report path.

**Acceptance Scenarios**:

1. **Given** a pipeline run has completed, **When** all episodes are processed, **Then** a results summary panel appears showing per-episode status with icons.
2. **Given** the results summary is displayed, **When** there are missing fonts, **Then** the summary lists all genuine font misses with their names.
3. **Given** the results summary is displayed, **When** the operator sees the report path, **Then** the path points to the `_AnimeStudio_Report.md` file in the library directory.
4. **Given** the results summary is displayed, **When** the operator wants to run again, **Then** a "Run Again" or "Back to Dashboard" button is available.

---

### User Story 5 - Error Presentation & Notifications (Priority: P2)

When errors occur during the pipeline (tool not found, mux failure, encoding issues), the TUI presents them as styled notification widgets or inline error panels — never raw tracebacks. Critical errors that halt the pipeline show a modal dialog; non-critical errors appear as dismissible notifications.

**Why this priority**: Proper error presentation prevents operator confusion and aligns with Constitution Principle IV (structured error handling). Important but lower than core flow since the activity feed already surfaces most issues.

**Independent Test**: Can be tested by simulating tool failures and verifying styled error notifications appear instead of raw exceptions.

**Acceptance Scenarios**:

1. **Given** a pipeline run is in progress, **When** a `ToolNotFoundError` occurs, **Then** a modal dialog appears with the tool name, installation instructions, and a "Dismiss" button.
2. **Given** a pipeline run is in progress, **When** a non-critical error occurs (e.g., font match failure for one episode), **Then** a dismissible toast notification appears with the error summary.
3. **Given** errors have occurred, **When** the pipeline completes, **Then** the results summary includes an error count and the errors are accessible for review.
4. **Given** any error presentation, **When** the error widget renders, **Then** it never displays raw Python tracebacks or stderr dumps.

---

### User Story 6 - Dry-Run Mode Toggle (Priority: P3)

The operator can toggle a "Dry Run" checkbox on the dashboard before initiating a pipeline run. When enabled, the pipeline simulates all operations without modifying any files on disk. The activity feed and progress indicators work identically, but entries are tagged with a "[DRY RUN]" label.

**Why this priority**: Dry-run support already exists in `PipelineConfig`. This story wires it to the TUI — useful for testing but not essential for the core workflow.

**Independent Test**: Can be tested by enabling dry-run, running a pipeline, and verifying no files are modified while the activity feed still shows simulated events.

**Acceptance Scenarios**:

1. **Given** the dashboard is displayed, **When** the operator toggles the "Dry Run" checkbox, **Then** the checkbox state persists until changed.
2. **Given** dry-run is enabled, **When** the operator presses "Run Pipeline", **Then** the pipeline runs with `PipelineConfig(dry_run=True)` and a "[DRY RUN]" banner is visible.
3. **Given** dry-run mode is active, **When** the pipeline completes, **Then** no files on disk are modified, moved, or created.

---

### Edge Cases

- What happens when the library path is not accessible (permission denied)?
  - The TUI displays a styled error notification and does not attempt to run the pipeline.
- What happens when the pipeline is already running and the operator tries to start another?
  - The "Run Pipeline" button is disabled during an active run; a toast notification explains why.
- What happens when the terminal window is very small (< 80x24)?
  - The TUI gracefully degrades, hiding non-essential panels and showing a minimum viable layout.
- What happens when structlog emits very high-frequency events (e.g., per-font-query)?
  - The activity feed batches/throttles updates to avoid overwhelming the Textual event loop (max ~10 updates/second rendered).
- What happens when the user resizes the terminal during a pipeline run?
  - Textual handles terminal resize natively; layout reflowed without interrupting the pipeline.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: TUI MUST be implemented as a Textual 1.x `App` subclass in `src/tui/app.py`.
- **FR-002**: TUI MUST consume `PipelineRunner` exclusively via dependency injection — no direct filesystem, subprocess, or network I/O in the TUI layer.
- **FR-003**: TUI MUST display a dashboard screen with library path input, dry-run toggle, and "Run Pipeline" action button.
- **FR-004**: TUI MUST display a real-time activity feed derived from structlog INFO+ events during pipeline execution.
- **FR-005**: TUI MUST display progress indicators: spinner for library scanning, determinate progress bar for mux job completion (N/M).
- **FR-006**: TUI MUST display a results summary panel after pipeline completion with per-episode status, font statistics, and report path.
- **FR-007**: TUI MUST present errors via styled Textual notification widgets (toast/modal), never via raw tracebacks or stderr dumps.
- **FR-008**: TUI MUST use Textual's `run_worker()` for all background pipeline operations — no manual thread creation.
- **FR-009**: TUI MUST support dry-run mode via a dashboard toggle that sets `PipelineConfig(dry_run=True)`.
- **FR-010**: TUI MUST use Textual CSS for all styling — no inline Rich markup for layout concerns.
- **FR-011**: Activity feed MUST throttle rendering to prevent event loop starvation (max ~10 UI updates/second).
- **FR-012**: TUI MUST disable the "Run Pipeline" button during an active pipeline run to prevent concurrent runs.
- **FR-013**: TUI MUST use Textual's built-in keybinding system for navigation (e.g., `q` to quit, `d` for dark/light mode toggle).

### Key Entities

- **DashboardScreen**: Main TUI screen composing header, path input, controls, and status panels.
- **ActivityFeed**: Widget displaying real-time curated log entries from structlog events.
- **ProgressPanel**: Widget composing scanner spinner + mux progress bar + font resolution indicators.
- **ResultsSummary**: Widget displaying post-pipeline completion summary with episode statuses.
- **ErrorModal**: Modal dialog for critical errors with structured messages and remediation hints.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operator can launch the TUI, enter a library path, and initiate a pipeline run within 30 seconds of first launch.
- **SC-002**: Activity feed entries appear within 500ms of the corresponding structlog event being emitted.
- **SC-003**: Progress bar accurately reflects mux job completion ratio (N/M) with no more than 1-second lag.
- **SC-004**: All pipeline errors are presented as styled widgets — zero raw tracebacks visible in the TUI under any failure scenario.
- **SC-005**: TUI renders correctly on terminals sized 80x24 and larger without layout overflow.
- **SC-006**: Dry-run mode produces zero filesystem modifications while displaying full activity feed and progress.
- **SC-007**: TUI layer contains zero direct imports from `src/adapters/`, `src/hunters/`, or `subprocess`/`httpx`/`os`/`shutil` modules.

## Assumptions

- Textual 1.x is installed and available in the project virtual environment (already an approved dependency per constitution).
- The `PipelineRunner` API from Phase 4 is stable and complete — the TUI consumes it as-is.
- structlog is configured project-wide; the TUI taps into the logging pipeline via a custom log handler or processor, not by replacing the logging config.
- The terminal supports 256-color mode (Textual requirement); true-color is preferred but not required.
- The TUI is the sole presentation layer — no parallel CLI interface is built in this phase.
- The entry point (`src/__main__.py`) will be updated to launch the TUI app.
