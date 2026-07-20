# Feature Specification: Pipeline Control & Safety (Phase 7.5)

**Feature Branch**: `010-pipeline-control-safety`

**Created**: 2026-06-07

**Status**: Draft

**Input**: User description: "Smart Stop + Checkpoint, Multi-level Undo System, Fix 4 failing tests"

## User Scenarios & Testing

### User Story 1 - Graceful Pipeline Stop with Checkpoint (Priority: P1)

A user starts a pipeline run on a large anime library (100+ episodes).
Midway through, they realize they selected the wrong library or need to
shut down. They click "Stop" — the system finishes the current episode
(no data corruption), saves progress, and stops. Next time they run
the same library, a dialog offers to resume from where they left off.

**Why this priority**: Without graceful stop, the only option is
force-closing the app, risking corrupted MKV files and lost progress.
This is the most critical safety feature.

**Independent Test**: Can be fully tested by starting a multi-episode
dry-run, clicking Stop after 2 episodes, verifying checkpoint file
exists, then starting a new run and confirming the Resume dialog
appears with correct episode count.

**Acceptance Scenarios**:

1. **Given** a pipeline is processing episode 5 of 20, **When** user
   clicks the Stop button, **Then** episode 5 finishes completely
   (muxed and trashed), episodes 6-20 are not started, and a checkpoint
   file is written to `.anime_studio/pipeline_checkpoint.toml`.

2. **Given** a checkpoint exists for library path `/anime/HxH`,
   **When** user starts a new run for the same library, **Then** a
   dialog appears with three options: "Resume (skip 5 completed)",
   "Start Fresh", or "Cancel".

3. **Given** user selects "Resume", **When** the pipeline runs,
   **Then** only episodes 6-20 are processed; episodes 1-5 are skipped
   entirely.

4. **Given** user selects "Start Fresh", **When** the pipeline runs,
   **Then** the checkpoint file is deleted and all 20 episodes are
   processed from scratch.

5. **Given** a checkpoint exists for library `/anime/HxH` but user
   runs a different library `/anime/Mushishi`, **Then** no resume
   dialog appears; the pipeline runs normally.

---

### User Story 2 - Undo Pipeline Operations (Priority: P2)

After a pipeline run processes an entire anime library, the user
discovers the subtitles were wrong (e.g., wrong language). They open
the Undo dialog, select the run, and restore all original files from
the trash directory — undoing the entire batch operation.

**Why this priority**: The existing trash system protects files for
30 days, but there is no user-facing way to restore them. Users must
manually navigate `.anime_studio_trash/` and rename files. This feature
surfaces that capability through a clean UI.

**Independent Test**: Run pipeline on 3 episodes → open Undo dialog →
select "Undo entire run" → verify original MKV and ASS files are
restored to their original locations.

**Acceptance Scenarios**:

1. **Given** a completed pipeline run, **When** user opens the Undo
   dialog, **Then** the most recent run is shown with episode count,
   timestamp, and library path.

2. **Given** the Undo dialog is open, **When** user selects "Undo
   entire run" and clicks "Undo Selected", **Then** all original files
   are restored from `.anime_studio_trash/` to their original paths,
   and the muxed files (which replaced them) are removed.

3. **Given** the Undo dialog is open, **When** user selects "Undo by
   show" and checks only "Hunter x Hunter", **Then** only Hunter x
   Hunter episodes are restored; other shows remain processed.

4. **Given** the Undo dialog is open, **When** user selects "Undo
   specific episode" and picks episode 5, **Then** only episode 5's
   original MKV and ASS are restored.

5. **Given** a trash file has been auto-purged (older than 30 days),
   **When** user attempts to undo that episode, **Then** a warning
   is shown: "Original file no longer available (auto-purged)".

6. **Given** a file already exists at the restore destination (user
   manually placed a file there), **When** undo is attempted, **Then**
   the system asks for confirmation before overwriting.

---

### User Story 3 - Fix Existing Test Failures (Priority: P1)

Four tests are currently failing due to model/implementation
mismatches from Phase 7 changes. These MUST be fixed to maintain
the test-first quality gate (248 tests, 100% pass rate).

**Why this priority**: Tied with P1 — broken tests block all
development. No feature work should proceed on a red test suite.

**Independent Test**: Run `uv run pytest tests/unit/ -v` and verify
all 248+ tests pass.

**Acceptance Scenarios**:

1. **Given** `test_is_excluded_amux_temp_file` fails because
   `_is_excluded()` checks `path.is_file()` on non-existent test
   paths, **When** the check is changed to pattern-only (no filesystem
   call), **Then** the test passes.

2. **Given** `test_pipeline_runner_respects_selected_paths` fails
   because `.resolve()` on mock paths changes the expected value,
   **When** the assertion is updated to match the actual filtering
   behavior, **Then** the test passes.

3. **Given** `test_gui_boundary_integrity` fails because
   `main_window.py` or `log_bridge.py` has a static `src.core.*`
   import, **When** the import is moved inside the function (lazy/
   dynamic), **Then** the boundary test passes.

4. **Given** `test_main_window_two_phase_run_flow` fails because
   the test uses old model types (`ShowNode` with wrong fields),
   **When** the test is rewritten to match the current two-phase
   flow (auto-scan on library select → tree → Run Selected),
   **Then** the test passes.

---

### Edge Cases

- What happens when the checkpoint file is corrupted or has invalid TOML?
  → Treat as "no checkpoint" — log warning and proceed normally.
- What happens when the user stops during the font ingestion pre-step
  (before any episode processing)? → No checkpoint written (nothing to
  resume); pipeline returns cleanly.
- What happens when the run_history directory has >10 manifests?
  → Auto-prune oldest beyond the configured limit.
- What happens when the user tries to undo while a pipeline is running?
  → Undo button is disabled during pipeline execution.
- What happens when `.anime_studio/` directory doesn't exist?
  → Create it on first checkpoint/manifest write.

## Requirements

### Functional Requirements

#### Feature 1: Smart Stop + Checkpoint

- **FR-001**: System MUST accept an `asyncio.Event` as a stop signal
  in `PipelineRunner.run()`. The event is checked between episodes.
- **FR-002**: When stop is signaled, the system MUST finish the
  currently-processing episode before stopping.
- **FR-003**: After stop, the system MUST write a checkpoint file to
  `.anime_studio/pipeline_checkpoint.toml` with: `library_path`,
  `completed_episodes` (list), `timestamp`, `selected_paths` (list).
- **FR-004**: On pipeline start, the system MUST check for an existing
  checkpoint matching the current `library_path` and offer Resume /
  Start Fresh / Cancel.
- **FR-005**: Resume MUST skip episodes listed in `completed_episodes`.
- **FR-006**: Start Fresh MUST delete the checkpoint and process all.
- **FR-007**: The GUI MUST provide a Stop button that is visible only
  during pipeline execution.
- **FR-008**: The Stop button MUST call `stop_event.set()` — never
  terminate the process or cancel asyncio tasks directly.

#### Feature 2: Undo System

- **FR-010**: System MUST write a run manifest after each pipeline
  completion to `.anime_studio/run_history/run_YYYY-MM-DD_HH-MM-SS.toml`.
- **FR-011**: Run manifest MUST contain: `run_id` (UUID), `timestamp`,
  `library_path`, and `episodes_processed` (list of episode records
  with `episode_path`, `trash_receipt`, `show_name`, `status`).
- **FR-012**: System MUST support three undo levels: single episode,
  by show, and full run.
- **FR-013**: Undo MUST restore original files from
  `.anime_studio_trash/` to their original paths.
- **FR-014**: Undo MUST verify trash files exist before attempting
  restore. Missing files produce a non-fatal warning.
- **FR-015**: Undo MUST NOT overwrite existing files without user
  confirmation.
- **FR-016**: After successful undo, the manifest MUST be updated
  to reflect restored episodes.
- **FR-017**: System MUST keep a configurable number of run manifests
  (default: 10). Oldest manifests MUST be auto-pruned.
- **FR-018**: The GUI MUST provide an Undo dialog (`QDialog`) showing
  run history with radio-button undo level selection.
- **FR-019**: Undo dialog MUST be disabled during active pipeline runs.

#### Feature 3: Fix Failing Tests

- **FR-020**: `_is_excluded()` MUST NOT call `path.is_file()` for the
  `_amux_` pattern check — use filename pattern matching only.
- **FR-021**: `test_pipeline_runner_respects_selected_paths` MUST
  assert on the correct path values accounting for mock path behavior.
- **FR-022**: All GUI files MUST pass the AST boundary test (no static
  imports of `src.core`, `src.adapters`, `src.hunters`, `src.models`
  except via dynamic `importlib` in `bootstrap.py`).
- **FR-023**: MainWindow flow MUST be: library picked → auto-scan →
  tree shown → user selects → "Run Pipeline" processes only selected.

### Key Entities

- **RunManifest**: Represents one complete pipeline run. Contains run
  metadata and list of processed episodes with their trash receipts.
- **EpisodeProcessed**: One episode within a run manifest. Links
  `episode_path` to `trash_receipt` path for undo.
- **PipelineCheckpoint**: Snapshot of in-progress pipeline state.
  Contains library path and list of completed episode paths.

## Success Criteria

### Measurable Outcomes

- **SC-001**: User can stop a running pipeline and resume from the same
  point within 5 seconds of the stop action completing.
- **SC-002**: Checkpoint file is correctly written 100% of the time when
  stop is triggered (no data loss).
- **SC-003**: User can undo any of the last 10 pipeline runs at
  episode, show, or full-run granularity.
- **SC-004**: Undo restores files to their original locations with 100%
  fidelity (byte-identical to trash copy).
- **SC-005**: All existing tests (248+) continue to pass after changes.
- **SC-006**: The 4 specific failing tests are fixed and pass.
- **SC-007**: All new code passes `ruff check` (0 warnings) and
  `ruff format --check` (0 diffs).
- **SC-008**: All new code is fully typed (ready for `mypy --strict`).
- **SC-009**: AST boundary test passes with all new files included.

## Assumptions

- TOML is used for checkpoint and run manifest persistence (consistent
  with existing `config.toml` and `font_library.toml` patterns).
- `tomllib` (built-in 3.11+) handles reading. Writing uses manual TOML
  serialization or `tomli_w` (to be added as dev dependency if needed).
- The existing `.anime_studio_trash/` directory and `TrashReceipt`
  model are the foundation for undo — no new trash mechanism needed.
- The 30-day auto-purge limit means undo is only available for runs
  within the last 30 days. This is documented, not changed.
- Run manifests are local to the library directory (not global).
  `.anime_studio/run_history/` is inside the library root.
- The GUI auto-scan flow (library picked → immediate scan → tree)
  is the correct Phase 7 behavior that tests should validate.
