# Feature Specification: PySide6 Dashboard

**Feature Branch**: `007-pyside-dashboard`

**Created**: 2026-05-26

**Status**: Draft

**Input**: User description: "Replace failed Flet dashboard with robust PySide6 GUI. Modern dark-themed dashboard using qdarktheme. File picker for library path. Real-time activity feed via asyncio.Queue log bridge. Progress bars. Results table. Strict hexagonal bounds."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch & Select Library (Priority: P1)

The user launches Anime Studio and is presented with a modern, dark-themed dashboard window. They click a "Select Library" button which opens a native file dialog. After selecting their anime library folder, the path is displayed in the dashboard and persisted for future sessions.

**Why this priority**: Without library selection, no pipeline operation can begin. This is the entry gate for all functionality.

**Independent Test**: Can be fully tested by launching the app, clicking the file picker, selecting a folder, restarting, and verifying the path persists. Delivers a working window with theme and configuration.

**Acceptance Scenarios**:

1. **Given** the application is not running, **When** the user launches it, **Then** a dark-themed main window appears within 2 seconds with a "Select Library" button visible.
2. **Given** the main window is displayed, **When** the user clicks "Select Library", **Then** a native `QFileDialog` opens for directory selection.
3. **Given** the user selects a valid directory, **When** the dialog closes, **Then** the selected path is displayed in the dashboard and saved to `config.toml`.
4. **Given** the user previously selected a library path, **When** they relaunch the application, **Then** the previously selected path is pre-populated.

---

### User Story 2 - Real-Time Activity Feed (Priority: P2)

While the pipeline runs, the user sees a scrolling activity feed in the dashboard showing curated log events (INFO+ level). Events appear in real-time without freezing the GUI. The feed is read-only, auto-scrolls to the latest entry, and supports manual scroll-back to review history.

**Why this priority**: Real-time feedback during pipeline runs is critical for user confidence and debugging. Without it, the user has no visibility into what the system is doing.

**Independent Test**: Can be tested by starting a pipeline run and verifying that log events appear in the feed widget within 500ms of occurrence, the GUI remains responsive during event streaming, and scroll behavior works correctly.

**Acceptance Scenarios**:

1. **Given** the pipeline is running, **When** an INFO-level log event is emitted, **Then** it appears in the activity feed within 500ms.
2. **Given** the activity feed is displaying events, **When** the user does not interact with the feed, **Then** it auto-scrolls to show the most recent entry.
3. **Given** the activity feed has scrolled content, **When** the user scrolls up manually, **Then** auto-scroll pauses until the user scrolls back to the bottom.
4. **Given** events are streaming rapidly (>10/sec), **When** the GUI event loop processes them, **Then** the main window remains responsive (no freezing, frame drops, or input lag).

---

### User Story 3 - Progress Tracking (Priority: P3)

During long-running operations (muxing, font hunting, bulk processing), the user sees progress bars indicating completion percentage. Each active operation has its own progress bar. When an operation completes, its progress bar shows 100% and then transitions to a completion indicator.

**Why this priority**: Progress bars transform a "is it stuck?" experience into a predictable one. Essential for operations that take minutes.

**Independent Test**: Can be tested by triggering a multi-file muxing operation and verifying that individual progress bars appear, update smoothly, and reach 100% on completion.

**Acceptance Scenarios**:

1. **Given** a pipeline operation starts, **When** the operation emits progress events, **Then** a `QProgressBar` appears in the progress panel with the operation name.
2. **Given** a progress bar is displayed, **When** the operation progresses, **Then** the bar updates smoothly (no jumps larger than 20% at a time under normal conditions).
3. **Given** an operation completes successfully, **When** its progress reaches 100%, **Then** the bar displays a completion state (green tint or checkmark icon).
4. **Given** an operation fails, **When** the failure is detected, **Then** the progress bar displays an error state (red tint) with a brief error summary.

---

### User Story 4 - Results Table (Priority: P4)

After a pipeline run completes, the user sees a structured results table showing per-episode status: file name, subtitle status, font status, mux result, and any errors. The table supports sorting by any column and allows the user to copy cell contents.

**Why this priority**: The results table is the final deliverable view — it tells the user what succeeded and what needs attention. Important but depends on the pipeline producing results first.

**Independent Test**: Can be tested by completing a pipeline run on a small test library (3-5 episodes) and verifying the table populates with correct data, columns are sortable, and cell content is copyable.

**Acceptance Scenarios**:

1. **Given** a pipeline run has completed, **When** results are available, **Then** a table widget displays one row per processed episode.
2. **Given** the results table is populated, **When** the user clicks a column header, **Then** the table sorts by that column (ascending/descending toggle).
3. **Given** a row shows a failed operation, **When** the user hovers or clicks the error cell, **Then** a tooltip or expanded view shows the full error message with remediation suggestion.
4. **Given** the results table has data, **When** the user right-clicks a cell, **Then** a context menu offers "Copy" functionality.

---

### Edge Cases

- What happens when the selected library path becomes inaccessible (e.g., external drive disconnected)?
  - The dashboard MUST show a warning banner and disable pipeline operations until a valid path is selected.
- How does the system handle rapid-fire log events (100+/sec burst)?
  - Events MUST be batched and rendered in chunks (max 60 updates/sec to the widget) to prevent GUI starvation.
- What happens if the user closes the window during an active pipeline run?
  - The application MUST prompt for confirmation ("Pipeline is running. Cancel and exit?") before terminating. On confirmation, running subprocesses MUST be killed gracefully.
- How does the results table handle very large libraries (1000+ episodes)?
  - The table MUST use lazy loading or virtual scrolling to prevent memory exhaustion. Initial render MUST complete within 2 seconds.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a PySide6 main window with modern dark theme applied via `qdarktheme`.
- **FR-002**: System MUST provide a "Select Library" button that opens a `QFileDialog` for directory selection.
- **FR-003**: System MUST persist the selected library path in `config.toml` and restore it on next launch.
- **FR-004**: System MUST display a real-time activity feed widget showing curated INFO+ log events from the pipeline.
- **FR-005**: Activity feed MUST receive events via a thread-safe mechanism: either `qasync`-bridged `asyncio.Queue` consumption or Qt signal emission from a dedicated bridge, ensuring zero direct I/O from the GUI layer.
- **FR-006**: System MUST display `QProgressBar` widgets for active pipeline operations with percentage updates.
- **FR-007**: System MUST display a `QTableWidget` or `QTableView` showing pipeline results with sortable columns.
- **FR-008**: GUI layer MUST NOT perform any I/O directly — it MUST consume `PipelineRunner` (from `src/core/`) via dependency injection.
- **FR-009**: System MUST integrate asyncio and Qt event loops via `qasync.QEventLoop` on a single thread.
- **FR-010**: System MUST handle window close during active pipeline with a confirmation dialog and graceful subprocess cleanup.

### Key Entities

- **DashboardState**: Represents current GUI state — selected library path, active operations, feed entries, results data. Pure data, no I/O.
- **ProgressEvent**: Emitted by pipeline operations — operation name, percentage, status (running/complete/failed).
- **ActivityLogEntry**: Curated log event — timestamp, level, message, source module. Derived from structlog output.
- **PipelineResult**: Per-episode result — file name, subtitle status, font status, mux result, error details.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Application launches and displays themed main window within 2 seconds on a standard Windows machine.
- **SC-002**: File picker dialog opens within 500ms of button click.
- **SC-003**: Activity feed displays log events within 500ms of emission with no GUI freeze.
- **SC-004**: GUI remains responsive (accepts input, repaints) during pipeline runs with 100+ concurrent log events per second.
- **SC-005**: Results table populates within 2 seconds for libraries up to 500 episodes.
- **SC-006**: All progress bars update smoothly with no visible stutter during normal pipeline operations.
- **SC-007**: Zero direct I/O calls originate from any module under `src/gui/` (verifiable via import analysis).

## Assumptions

- PySide6 6.x is available via PyPI and compatible with Python 3.11+.
- `qasync` provides stable asyncio-Qt bridge without known blocking issues.
- `qdarktheme` applies a modern dark theme with a single `qdarktheme.setup_theme()` call.
- The existing `PipelineRunner` in `src/core/` exposes an async interface that emits `ProgressEvent` and `ActivityLogEntry` via `asyncio.Queue`.
- The user's Windows machine has a functional display server capable of rendering Qt windows.
- The `config.toml` infrastructure from prior features (001-004) is available and functional.
