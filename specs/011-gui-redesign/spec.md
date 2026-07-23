# Feature Specification: GUI Redesign — Two-Panel Layout

**Feature Branch**: `011-gui-redesign`

**Created**: 2026-06-27

**Status**: Complete — Phase 8 Human Manual PASS (2026-07-24) | 386 tests, ruff, format, mypy --strict passed | Phase 8 implementation baseline `fb3e95c`

**Input**: User description: "Phase 8a — GUI Redesign. Replace vertical-stack GUI with modern two-panel layout (sidebar + main panel). Fix inverted workflow, outdated layout, checkbox tree."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Select Show Then Process (Priority: P1)

User launches the application. The sidebar immediately shows all previously-added
anime shows (loaded from cached index, NOT by scanning). User clicks a show name
in the sidebar. The main panel populates with that show's episodes. User selects
specific episodes via checkboxes, clicks "Run N selected". Pipeline processes only
those episodes.

**Why this priority**: Fixes the #1 UX problem — the app currently auto-scans the
entire library (637 episodes, ~11 min) BEFORE the user can do anything. This is the
core workflow inversion that blocks usability.

**Independent Test**: Can be tested by launching the app with a cached index,
clicking a show, selecting episodes, and verifying only selected episodes are
processed.

**Acceptance Scenarios**:

1. **Given** the app has a cached show index, **When** user launches the app, **Then** the sidebar populates instantly (<1s) without scanning
2. **Given** a show is displayed in the sidebar, **When** user clicks it, **Then** the main panel shows that show's episodes with status badges
3. **Given** episodes are shown in the table, **When** user checks 5 episodes and clicks "Run 5 selected", **Then** only those 5 episodes are processed by the pipeline
4. **Given** no cached index exists, **When** user launches the app, **Then** the sidebar shows empty state with "Add Folder" prompt

---

### User Story 2 - Add New Show Folder (Priority: P1)

User clicks "Add Folder" button at the bottom of the sidebar. A native folder
dialog opens. User selects an anime folder. The app scans ONLY that folder
(not the entire library). The show appears in the sidebar with episode count.

**Why this priority**: This is the primary data entry flow — without it, users
cannot populate the sidebar.

**Independent Test**: Can be tested by clicking Add Folder, selecting a folder
with MKVs, and verifying it appears in the sidebar.

**Acceptance Scenarios**:

1. **Given** the sidebar is empty, **When** user clicks "Add Folder" and selects a valid anime directory, **Then** the show appears in the sidebar within 5 seconds
2. **Given** the sidebar has existing shows, **When** user adds a new folder, **Then** existing shows remain and the new show is appended
3. **Given** the user adds a folder with no MKV files, **When** scan completes, **Then** the show appears with "0 episodes" status and a warning icon

---

### User Story 3 - View Episode Status (Priority: P2)

User selects a show in the sidebar. The episode table shows each episode with
a visual status badge: Muxed (green), Pending (amber), Skipped (gray), Error
(red). User can see at a glance which episodes need processing.

**Why this priority**: Status visibility is essential for informed decision-making
but is not a blocker for basic functionality.

**Independent Test**: Can be tested by populating the table with mock episodes
in various states and verifying correct badge colors.

**Acceptance Scenarios**:

1. **Given** a show with mixed episode states, **When** user selects it, **Then** each episode row shows the correct status badge color
2. **Given** an episode was successfully muxed, **When** viewing the table, **Then** it shows a green "Muxed" badge
3. **Given** an episode has no subtitle match, **When** viewing the table, **Then** it shows a gray "Skipped" badge

---

### User Story 4 - Collapsible Activity Log (Priority: P3)

The activity log at the bottom of the main panel is collapsed by default (36px),
showing only a one-line summary. User clicks the chevron to expand it to full
height (max 160px) to view detailed logs.

**Why this priority**: Log viewing is a secondary concern during normal usage.
Collapsed default maximizes screen space for the episode table.

**Independent Test**: Can be tested by clicking the chevron button and verifying
the widget toggles between collapsed and expanded states.

**Acceptance Scenarios**:

1. **Given** the app is launched, **When** the main panel renders, **Then** the activity log is collapsed (36px height)
2. **Given** the log is collapsed, **When** user clicks the chevron, **Then** it expands to show log entries (max 160px)
3. **Given** the log is expanded, **When** user clicks the chevron again, **Then** it collapses back to 36px

---

### Edge Cases

- What happens when user adds a folder that is already in the sidebar? → Show warning, skip duplicate
- What happens when a cached show's folder no longer exists on disk? → Show "Missing" status icon, gray out
- What happens when user tries to run pipeline with zero episodes selected? → "Run 0 selected" button is disabled
- How does system handle a show with 500+ episodes in the table? → Qt MVC model handles 10K+ rows efficiently
- What happens when user clicks a show while another show's scan is in progress? → Queue or cancel previous scan
- What happens when the cached index TOML file is corrupted? → Log warning, treat as empty, rebuild on next scan

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a two-panel layout: sidebar (220px fixed width) + main panel
- **FR-002**: System MUST populate the sidebar from a cached TOML index on startup without scanning
- **FR-003**: Sidebar MUST show each show with a status icon, show name, and subtitle text (e.g. "12 ready / 2 processed")
- **FR-004**: Sidebar MUST emit a signal when a show is selected, providing show name and folder path
- **FR-005**: "Add Folder" button MUST scan ONLY the selected folder, NOT the entire library
- **FR-006**: Episode table MUST display columns: checkbox, episode name, subtitle match, status badge
- **FR-007**: Status badges MUST use distinct colors: Muxed (green), Pending (amber), Skipped (gray), Error (red)
- **FR-008**: Episode table MUST support "Select all" via header checkbox
- **FR-009**: "Run N selected" button label MUST update dynamically based on checkbox count
- **FR-010**: "Run N selected" button MUST be disabled when no episodes are selected
- **FR-011**: Activity feed MUST be collapsible with default collapsed state (36px)
- **FR-012**: Activity feed expanded state MUST have a maximum height of 160px
- **FR-013**: System MUST remove the `SelectionTreeWidget` and `LibraryPickerWidget` entirely
- **FR-014**: System MUST preserve existing functionality: closeEvent confirmation, Stop button, Undo button, drag-drop font import
- **FR-015**: Full library rescan MUST only occur via explicit "Refresh" action or Settings
- **FR-016**: Cached show index MUST persist to a TOML file in `.anime_studio/`
- **FR-017**: Header bar (44px) MUST show app name, library path, and settings icon
- **FR-018**: All existing 271 tests MUST still pass after changes (with appropriate test rewrites)

### Key Entities

- **ShowSummary**: Represents one show in the sidebar (name, path, status, episode count, processed count, subtitle text)
- **ShowStatus**: Enum of sidebar status states (pending, processing, ready, all_done, no_subtitle, warning)
- **ShowIndex**: Cached TOML file mapping show names to folder paths and status

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Application startup with cached index completes in under 1 second (vs current ~11 minutes with full scan)
- **SC-002**: Adding a single folder completes scanning in under 10 seconds for a typical show (12-26 episodes)
- **SC-003**: Episode table renders 500+ episodes without perceptible lag
- **SC-004**: All existing 271 tests pass after migration (with appropriate rewrites)
- **SC-005**: At least 15 new tests cover the new widgets and services
- **SC-006**: No constitution violations (verified by AST boundary test)
- **SC-007**: `ruff check`, `ruff format --check`, and `mypy --strict` all pass with zero errors

## Assumptions

- PySide6 QTableView with QAbstractTableModel handles 10K+ rows efficiently (proven by Qt documentation)
- Cached TOML index is small enough (<100KB even for 100+ shows) that sync reads are acceptable for startup
- Users have at most ~100 shows in their library (reasonable for personal anime collections)
- The existing `LibraryScanner.scan()` method can be adapted to scan single folders without a full rewrite
- `ResultsTableWidget` remains separate from `EpisodeTableWidget` (selection vs post-run results are distinct concerns)
- Font drag-drop continues to target `MainWindow` directly (not the sidebar)
