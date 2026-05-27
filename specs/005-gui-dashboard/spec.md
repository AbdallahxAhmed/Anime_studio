# Feature Specification: GUI Dashboard

**Feature Branch**: `006-gui-dashboard`

**Created**: 2026-05-26

**Status**: Draft

**Input**: User description: "Replace the old dashboard with a modern GUI. Build a robust graphical dashboard as a pure consumer of PipelineRunner. Material Design interface with path picker, real-time activity feed from structured logging, async progress indicators, post-run results table, and strict hexagonal architecture bounds."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch Dashboard & Library Selection (Priority: P1)

The operator launches Anime Studio and sees a polished dashboard screen with a clean Material Design layout. The dashboard shows a welcome header, a directory picker for selecting the anime library path, and a "Run Pipeline" action button. The operator selects a library folder and initiates the pipeline run.

**Why this priority**: Without a launchable dashboard with library selection, no other functionality can be demonstrated. This is the entry point for all subsequent user stories.

**Independent Test**: Can be fully tested by launching the app, verifying the dashboard renders correctly, selecting a folder via the directory picker, and pressing "Run Pipeline". Delivers a usable entry point even if progress/logging isn't wired yet.

**Acceptance Scenarios**:

1. **Given** the application is launched, **When** the GUI initializes, **Then** the dashboard screen displays within 2 seconds with a header, directory picker, and "Run Pipeline" button.
2. **Given** the dashboard is displayed, **When** the operator selects a valid directory via the picker, **Then** the selected path is shown and the "Run Pipeline" button becomes active.
3. **Given** the dashboard is displayed, **When** the operator has not selected any path, **Then** the "Run Pipeline" button remains disabled.
4. **Given** a valid path is selected, **When** the operator presses "Run Pipeline", **Then** the dashboard transitions to the pipeline execution view, delegating the actual run to `PipelineRunner`.

---

### User Story 2 - Real-Time Activity Feed (Priority: P1)

During a pipeline run, the operator sees a live activity feed panel showing curated, human-readable messages derived from structured log events (INFO level and above). The feed auto-scrolls to show the latest entry but allows the operator to scroll back to review past entries. Each entry includes a timestamp, event category, and message. Updates are batched/throttled to keep the interface responsive.

**Why this priority**: Real-time feedback is critical for operator trust and debugging. Without a visible activity feed, the operator has no confirmation that the pipeline is working or insight into what's happening.

**Independent Test**: Can be tested by running a pipeline and verifying that INFO-level log events appear in the feed panel in real time with correct timestamps and formatting, and that the UI remains responsive under high-frequency event bursts.

**Acceptance Scenarios**:

1. **Given** a pipeline run is in progress, **When** an INFO-level log event is emitted (e.g., "library scan started"), **Then** a formatted entry appears in the activity feed within 500ms.
2. **Given** the activity feed is displaying events, **When** a WARNING or ERROR event is emitted, **Then** the entry is visually distinguished (color/icon) from INFO entries.
3. **Given** the feed has more entries than the visible area, **When** new entries arrive, **Then** the feed auto-scrolls to show the latest entry.
4. **Given** the feed is auto-scrolling, **When** the operator manually scrolls up, **Then** auto-scroll pauses; when the operator scrolls back to the bottom, auto-scroll resumes.
5. **Given** very high-frequency log events are emitted (e.g., per-font-query), **When** the feed renders updates, **Then** updates are batched so the UI remains responsive (max ~10 rendered updates per second).

---

### User Story 3 - Progress Tracking for Long-Running Operations (Priority: P1)

The operator sees distinct visual progress indicators for long-running operations: an indeterminate spinner for the Library Scanner, and a determinate progress bar for concurrent mux jobs (showing N/M completed).

**Why this priority**: Without progress indicators, the operator cannot distinguish a slow pipeline from a hung one. Progress bars for mux operations directly address the "12-episode series in <10 minutes" performance visibility goal.

**Independent Test**: Can be tested by running a pipeline on a multi-episode library and verifying the progress bar updates correctly as episodes complete muxing, and that the scanner shows a spinner while scanning.

**Acceptance Scenarios**:

1. **Given** a pipeline run is initiated, **When** the library scanner begins, **Then** a spinner or indeterminate progress indicator is displayed with a "Scanning library..." label.
2. **Given** the library scan completes and mux jobs begin, **When** a mux job finishes, **Then** the progress bar advances (e.g., "Muxing: 3/12 episodes complete").
3. **Given** multiple mux jobs are running concurrently, **When** progress updates are emitted, **Then** the progress bar accurately reflects the total completed vs. total planned.
4. **Given** all mux jobs complete, **When** the pipeline finishes, **Then** the progress indicator shows 100% and a summary replaces it (e.g., "✓ 12/12 episodes muxed").

---

### User Story 4 - Post-Run Results Table (Priority: P2)

After a pipeline run completes, the operator sees a structured results table showing per-episode status (✓ complete, ⚠ partial, ✗ failed), total fonts found/missing, total duration, and a reference to the generated report file. The table is sortable and scannable.

**Why this priority**: Post-run summary gives the operator actionable information about what succeeded and what needs attention. Less critical than real-time feedback but essential for workflow completion.

**Independent Test**: Can be tested by completing a pipeline run and verifying the results table appears with accurate episode counts, font stats, and report path.

**Acceptance Scenarios**:

1. **Given** a pipeline run has completed, **When** all episodes are processed, **Then** a results table appears showing per-episode status with visual indicators.
2. **Given** the results table is displayed, **When** there are missing fonts, **Then** the table lists all genuine font misses with their names.
3. **Given** the results table is displayed, **When** the operator sees the report path, **Then** the path points to the `_AnimeStudio_Report.md` file in the library directory.
4. **Given** the results table is displayed, **When** the operator wants to run again, **Then** a "Run Again" or "Back to Dashboard" button is available.
5. **Given** the results table is displayed, **When** the operator examines it, **Then** each row shows: episode name, status icon, font count, and any error summary.

---

### User Story 5 - Error Presentation & Notifications (Priority: P2)

When errors occur during the pipeline (tool not found, mux failure, encoding issues), the dashboard presents them as styled notification widgets or inline error panels — never raw tracebacks. Critical errors that halt the pipeline show a modal dialog; non-critical errors appear as dismissible notifications.

**Why this priority**: Proper error presentation prevents operator confusion and aligns with structured error handling principles. Important but lower than core flow since the activity feed already surfaces most issues.

**Independent Test**: Can be tested by simulating tool failures and verifying styled error notifications appear instead of raw exceptions.

**Acceptance Scenarios**:

1. **Given** a pipeline run is in progress, **When** a tool-not-found error occurs, **Then** a modal dialog appears with the tool name, installation instructions, and a "Dismiss" button.
2. **Given** a pipeline run is in progress, **When** a non-critical error occurs (e.g., font match failure for one episode), **Then** a dismissible notification appears with the error summary.
3. **Given** errors have occurred, **When** the pipeline completes, **Then** the results table includes an error count and the errors are accessible for review.
4. **Given** any error presentation, **When** the error widget renders, **Then** it never displays raw tracebacks or internal debug dumps.

---

### User Story 6 - Dry-Run Mode Toggle (Priority: P3)

The operator can toggle a "Dry Run" checkbox on the dashboard before initiating a pipeline run. When enabled, the pipeline simulates all operations without modifying any files on disk. The activity feed and progress indicators work identically, but entries are tagged with a "[DRY RUN]" label.

**Why this priority**: Dry-run support already exists in the pipeline configuration. This story wires it to the dashboard — useful for testing but not essential for the core workflow.

**Independent Test**: Can be tested by enabling dry-run, running a pipeline, and verifying no files are modified while the activity feed still shows simulated events.

**Acceptance Scenarios**:

1. **Given** the dashboard is displayed, **When** the operator toggles the "Dry Run" checkbox, **Then** the checkbox state persists until changed.
2. **Given** dry-run is enabled, **When** the operator presses "Run Pipeline", **Then** the pipeline runs in simulation mode and a "[DRY RUN]" banner is visible.
3. **Given** dry-run mode is active, **When** the pipeline completes, **Then** no files on disk are modified, moved, or created.

---

### Edge Cases

- What happens when the library path is not accessible (permission denied)?
  - The dashboard displays a styled error notification and does not attempt to run the pipeline.
- What happens when the pipeline is already running and the operator tries to start another?
  - The "Run Pipeline" button is disabled during an active run; a notification explains why.
- What happens when the application window is very small?
  - The dashboard gracefully degrades, prioritizing essential panels and using scrollable layout.
- What happens when very high-frequency log events are emitted (e.g., per-font-query)?
  - The activity feed batches/throttles updates to avoid overwhelming the UI event loop (max ~10 updates/second rendered).
- What happens when the user resizes the application window during a pipeline run?
  - Layout reflows without interrupting the pipeline.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dashboard MUST consume `PipelineRunner` exclusively via dependency injection — no direct filesystem, subprocess, or network I/O in the presentation layer.
- **FR-002**: The dashboard MUST display a main screen with a directory picker, dry-run toggle, and "Run Pipeline" action button.
- **FR-003**: The dashboard MUST display a real-time activity feed derived from structured log events (INFO level and above) during pipeline execution.
- **FR-004**: The dashboard MUST display progress indicators: an indeterminate spinner for library scanning, and a determinate progress bar for mux job completion (N/M).
- **FR-005**: The dashboard MUST display a structured results table after pipeline completion with per-episode status, font statistics, and report path.
- **FR-006**: The dashboard MUST present errors via styled notification widgets (dismissible for non-critical, modal for critical), never via raw tracebacks or debug dumps.
- **FR-007**: The dashboard MUST run all pipeline operations asynchronously — the UI must never freeze during long-running operations.
- **FR-008**: The dashboard MUST support dry-run mode via a dashboard toggle that configures the pipeline to simulate without file modifications.
- **FR-009**: The activity feed MUST throttle rendering to prevent UI event loop starvation (max ~10 UI updates per second).
- **FR-010**: The dashboard MUST disable the "Run Pipeline" button during an active pipeline run to prevent concurrent runs.
- **FR-011**: The directory picker MUST allow the operator to browse and select a folder, showing the selected path before pipeline execution.
- **FR-012**: The results table MUST show per-episode rows with: episode name, status indicator, font count, and error summary.
- **FR-013**: The dashboard MUST follow Material Design visual principles for a clean, modern appearance.

### Key Entities

- **Dashboard View**: Main screen composing header, directory picker, controls, and status panels.
- **Activity Feed**: Panel displaying real-time curated log entries from structured log events.
- **Progress Panel**: Area composing scanner spinner + mux progress bar indicators.
- **Results Table**: Structured table displaying post-pipeline completion summary with per-episode statuses.
- **Error Dialog**: Modal dialog for critical errors with structured messages and remediation hints.
- **Error Notification**: Dismissible notification for non-critical errors.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operator can launch the dashboard, select a library path, and initiate a pipeline run within 30 seconds of first launch.
- **SC-002**: Activity feed entries appear within 500ms of the corresponding log event being emitted.
- **SC-003**: Progress bar accurately reflects mux job completion ratio (N/M) with no more than 1-second lag.
- **SC-004**: All pipeline errors are presented as styled widgets — zero raw tracebacks visible in the dashboard under any failure scenario.
- **SC-005**: Dashboard remains responsive (UI interactions respond within 200ms) even during peak pipeline activity with high-frequency log events.
- **SC-006**: Dry-run mode produces zero filesystem modifications while displaying full activity feed and progress.
- **SC-007**: Results table correctly displays all episode statuses and font statistics within 2 seconds of pipeline completion.
- **SC-008**: Presentation layer contains zero direct imports from adapter, hunter, or low-level I/O modules.

## Assumptions

- The `PipelineRunner` API from previous phases is stable and complete — the dashboard consumes it as-is.
- Structured logging is configured project-wide; the dashboard taps into the logging pipeline via a custom handler or processor, not by replacing the logging config.
- The dashboard is the sole graphical presentation layer — no parallel interface is built in this phase.
- The entry point will be updated to launch the graphical dashboard.
- The previous dashboard implementation will be retired and its directory removed.
