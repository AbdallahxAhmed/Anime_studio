# Tasks: Pipeline Orchestration

**Input**: Design documents from `specs/004-pipeline/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included — spec references unit + integration tests per Constitution X.

**Organization**: Tasks grouped by user story for independent implementation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: New files and model additions needed before core pipeline work.

- [ ] T001 Create pipeline models (LibraryScanResult, EpisodeContext, PipelineConfig) in src/models/pipeline.py
- [ ] T002 Update src/models/__init__.py to export new pipeline models
- [ ] T003 [P] Create FilesystemPort protocol in src/ports/filesystem.py
- [ ] T004 [P] Update src/ports/__init__.py to export FilesystemPort
- [ ] T005 Add `MuxIntegrityError` to src/errors.py if not already present

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Adapters and core services that all user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T006 Implement FilesystemAdapter (move_to_trash, write_file_atomic, ensure_directory) in src/adapters/filesystem.py
- [ ] T007 [P] Implement MkvmergeAdapter (build mkvmerge CLI args from MuxJob, invoke via SubprocessAdapter, parse JSON output) in src/adapters/mkvmerge.py
- [ ] T008 [P] Implement AlassAdapter (build alass CLI args, invoke via SubprocessAdapter) in src/adapters/alass.py
- [ ] T009 [P] Implement FfsubsyncAdapter (build ffsubsync CLI args, invoke via SubprocessAdapter) in src/adapters/ffsubsync.py
- [ ] T010 Update src/adapters/__init__.py to export new adapters (FilesystemAdapter, MkvmergeAdapter, AlassAdapter, FfsubsyncAdapter)
- [ ] T011 Implement library_scanner.scan_library() in src/core/library_scanner.py — discover MKV/ASS pairs by stem matching, offload via asyncio.to_thread()
- [ ] T012 [P] Implement mux_planner.plan_mux() in src/core/mux_planner.py — build MuxJob from EpisodeContext (episode_path, subtitle_path, resolved_fonts, output_path, dry_run)
- [ ] T013 [P] Implement report_writer.render_report() and render_incremental_section() in src/core/report_writer.py — render PipelineReport → markdown string with tables, status symbols (✓/⚠/✗), per-font details
- [ ] T014 Update src/core/__init__.py to export scan_library, plan_mux, render_report, render_incremental_section, PipelineRunner

**Checkpoint**: Foundation ready — all adapters and stateless core services operational. Pipeline runner can now be built.

---

## Phase 3: User Story 1 — Full Library Pipeline Run (Priority: P1) 🎯 MVP

**Goal**: End-to-end pipeline: scan → repair → resolve fonts → plan mux → dispatch mux → trash → report.

**Independent Test**: Point pipeline at folder with 2–3 MKV/ASS pairs, verify output MKVs, trash receipts, and report.

### Tests for User Story 1

- [ ] T015 [P] [US1] Unit test for scan_library() in tests/unit/core/test_library_scanner.py — test stem matching, empty dir, MKV without ASS, case-insensitive
- [ ] T016 [P] [US1] Unit test for plan_mux() in tests/unit/core/test_mux_planner.py — test MuxJob construction from EpisodeContext, dry_run flag propagation
- [ ] T017 [P] [US1] Unit test for render_report() in tests/unit/core/test_report_writer.py — test markdown output contains timestamp, duration, episode table, font details
- [ ] T018 [P] [US1] Unit test for PipelineRunner.run() in tests/unit/core/test_pipeline_runner.py — test full pipeline with mocked adapters: scanner → repair → resolve → mux → trash → report
- [ ] T019 [P] [US1] Unit test for pipeline models in tests/unit/models/test_pipeline_models.py — test LibraryScanResult, EpisodeContext (frozen, model_copy), PipelineConfig

### Implementation for User Story 1

- [ ] T020 [US1] Implement PipelineRunner class in src/core/pipeline_runner.py — constructor accepts FontResolver, SubprocessPort, FilesystemPort, ToolRegistry, AppConfig
- [ ] T021 [US1] Implement PipelineRunner._process_episode() — single episode: repair ASS → extract fonts → resolve each font → plan mux → dispatch mux → generate trash receipts. Return EpisodeContext.
- [ ] T022 [US1] Implement PipelineRunner.run() — scan library → process all episodes (sequential analysis, concurrent mux dispatch via semaphore) → build PipelineReport → write report file
- [ ] T023 [US1] Implement semaphore-gated mux dispatch in PipelineRunner — acquire asyncio.Semaphore(config.max_concurrent_disk_io) before invoking MkvmergeAdapter
- [ ] T024 [US1] Implement dry-run guard in PipelineRunner — skip mux dispatch, skip trash move, still generate report
- [ ] T025 [US1] Implement graceful per-episode error handling — catch exceptions per episode, record in EpisodeContext.errors, set status=FAILED, continue to next
- [ ] T026 [US1] Wire report writing — call render_report() and write to `{library_path}/_AnimeStudio_Report.md` via FilesystemAdapter.write_file_atomic()

**Checkpoint**: Full pipeline functional end-to-end. US1 independently testable.

---

## Phase 4: User Story 2 — Subtitle Sync Fallback Chain (Priority: P2)

**Goal**: When sync_enabled, invoke alass→ffsubsync fallback chain per episode.

**Independent Test**: Provide offset ASS file, verify sync is attempted, fallback fires on failure.

### Tests for User Story 2

- [ ] T027 [P] [US2] Unit test for subtitle sync fallback logic in tests/unit/core/test_pipeline_runner.py — test alass success path, alass fail→ffsubsync path, both fail path
- [ ] T028 [P] [US2] Unit test for AlassAdapter in tests/unit/adapters/test_alass.py — test command construction, timeout, ToolResult parsing
- [ ] T029 [P] [US2] Unit test for FfsubsyncAdapter in tests/unit/adapters/test_ffsubsync.py — test command construction, timeout, ToolResult parsing

### Implementation for User Story 2

- [ ] T030 [US2] Implement PipelineRunner._sync_subtitle() — check sync_enabled, check alass availability in ToolRegistry, attempt alass, on failure attempt ffsubsync, return SyncResult
- [ ] T031 [US2] Integrate _sync_subtitle() into _process_episode() — call after repair, before font resolution. Update EpisodeContext with sync_result.
- [ ] T032 [US2] Handle both-fail scenario — record both tool outputs in EpisodeContext.errors, mark episode PARTIAL, leave original subtitle untouched

**Checkpoint**: Sync fallback chain operational. US2 independently testable.

---

## Phase 5: User Story 3 — Trash Receipt Tracking (Priority: P3)

**Goal**: Generate TrashReceipts for displaced files, execute moves, include in report.

**Independent Test**: Run pipeline on single episode, verify original in `.anime_studio_trash/`, receipt in report.

### Tests for User Story 3

- [ ] T033 [P] [US3] Unit test for FilesystemAdapter.move_to_trash() in tests/unit/adapters/test_filesystem.py — test file move, directory creation, permission error handling
- [ ] T034 [P] [US3] Unit test for trash receipt integration in tests/unit/core/test_pipeline_runner.py — test receipts generated per displaced file, receipt data in report

### Implementation for User Story 3

- [ ] T035 [US3] Implement trash receipt generation in _process_episode() — call SubtitleFile.plan_trash_disposal() for original ASS before mux, collect receipts
- [ ] T036 [US3] Implement trash execution in PipelineRunner — after successful mux, call FilesystemAdapter.move_to_trash() for each receipt (skip in dry_run)
- [ ] T037 [US3] Include trash receipt data in EpisodeReport — add receipts to report model, render in markdown

**Checkpoint**: Trash tracking operational. US3 independently testable.

---

## Phase 6: User Story 4 — Pipeline Report Generation (Priority: P4)

**Goal**: Comprehensive markdown report with per-episode and per-font details.

**Independent Test**: Run pipeline, validate report schema.

### Tests for User Story 4

- [ ] T038 [P] [US4] Unit test for full report rendering in tests/unit/core/test_report_writer.py — test complete report with multiple episodes, mixed statuses, font details, genuine misses
- [ ] T039 [P] [US4] Unit test for incremental report rendering in tests/unit/core/test_report_writer.py — test append section with delimiter header

### Implementation for User Story 4

- [ ] T040 [US4] Enhance render_report() — add per-font resolution table (font name, source, layer, cache hit/miss), applied rules section, genuine misses with audit trail
- [ ] T041 [US4] Implement render_incremental_section() — wrap report in `## Incremental Run: {timestamp}` section for appending
- [ ] T042 [US4] Implement full-vs-incremental write logic in PipelineRunner — detect if existing report, full run → overwrite, partial run → append via incremental section

**Checkpoint**: Report generation complete. US4 independently testable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, documentation, and quality gates.

- [ ] T043 [P] Run `ruff check .` and `ruff format .` — fix all linting/formatting issues
- [ ] T044 [P] Run full test suite `pytest tests/unit/ -v` — verify 100% pass
- [ ] T045 [P] Verify all new modules have proper `__init__.py` exports
- [ ] T046 Update quickstart.md with actual usage examples post-implementation
- [ ] T047 Run integration test with sample MKV/ASS files (if available) — `pytest tests/integration/ -v -m integration`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — this is the MVP
- **US2 (Phase 4)**: Depends on Phase 2 + Phase 3 (T020-T022 must exist for sync integration)
- **US3 (Phase 5)**: Depends on Phase 2 + Phase 3 (T020-T022 must exist for trash integration)
- **US4 (Phase 6)**: Depends on Phase 2 + Phase 3 (report_writer must exist)
- **Polish (Phase 7)**: Depends on all user stories

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no dependencies on other stories
- **US2 (P2)**: Builds on PipelineRunner from US1 — adds sync step
- **US3 (P3)**: Builds on PipelineRunner from US1 — adds trash step
- **US4 (P4)**: Builds on report_writer from US1 — enhances report

### Within Each User Story

- Tests written first → verify they fail
- Models before services
- Core logic before adapter wiring
- Integration before polish

### Parallel Opportunities

- T003, T004 can parallel with T001, T002
- T007, T008, T009 can parallel with T006
- T012, T013 can parallel
- All US1 tests (T015-T019) can parallel
- US2 tests (T027-T029) can parallel
- US3 tests (T033-T034) can parallel
- US4 tests (T038-T039) can parallel
- T043, T044, T045 can parallel

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together:
Task: "Unit test for scan_library() in tests/unit/core/test_library_scanner.py"
Task: "Unit test for plan_mux() in tests/unit/core/test_mux_planner.py"
Task: "Unit test for render_report() in tests/unit/core/test_report_writer.py"
Task: "Unit test for PipelineRunner.run() in tests/unit/core/test_pipeline_runner.py"
Task: "Unit test for pipeline models in tests/unit/models/test_pipeline_models.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T014)
3. Complete Phase 3: User Story 1 (T015-T026)
4. **STOP and VALIDATE**: Run `pytest tests/unit/ -v`
5. Pipeline operational for basic library processing

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Test → MVP functional
3. Add US2 → Sync fallback chain operational
4. Add US3 → Trash safety complete
5. Add US4 → Rich reporting complete
6. Polish → Production quality

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- PipelineRunner is the central orchestrator — US2/US3/US4 all add behavior to it
- All adapters follow existing pattern: thin wrapper around SubprocessAdapter
- Constitution compliance verified in plan.md — all 13 principles satisfied
- Total tasks: 47
