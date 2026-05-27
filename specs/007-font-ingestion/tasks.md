# Tasks: Embedded Subtitle Extraction via mkvextract

**Input**: Design documents from `/specs/007-font-ingestion/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Organization**: Single user story (US1: Embedded Subtitle Extraction) decomposed into setup → foundational → implementation → tests → polish phases.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1 = Embedded Subtitle Extraction)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Config & Models)

**Purpose**: Add the `SubtitleConfig` and `EmbeddedTrack` domain model that all downstream components depend on.

- [x] T001 [P] Add `SubtitleConfig` model and `subtitle` field to `AppConfig`, update `save_to_toml()` and `load_from_toml()` to handle `[subtitle]` section in `src/config.py`
- [x] T002 [P] Add `EmbeddedTrack` model, refactor `EmbeddedSubInfo` to use `tracks: list[EmbeddedTrack]` with computed `track_count` and `languages` properties in `src/models/pipeline.py`
- [x] T003 Export `EmbeddedTrack` from `src/models/__init__.py`

**Checkpoint**: Config can load/save `[subtitle]` section. `EmbeddedSubInfo` stores per-track metadata. All existing model tests still pass.

---

## Phase 2: Foundational (Port & Adapter)

**Purpose**: Create the hexagonal boundary for `mkvextract` — MUST complete before core logic can use it.

**⚠️ CRITICAL**: No pipeline integration work can begin until the port+adapter pair exists.

- [x] T004 [P] Create `MkvextractPort` protocol with `extract_track()` method in `src/ports/mkvextract.py`
- [x] T005 [P] Export `MkvextractPort` from `src/ports/__init__.py`
- [x] T006 Create `MkvextractAdapter` implementing `extract_track()` via `SubprocessPort` in `src/adapters/mkvextract.py`
- [x] T007 Export `MkvextractAdapter` from `src/adapters/__init__.py`

**Checkpoint**: `MkvextractAdapter` can be instantiated with a `SubprocessPort` and called with `await adapter.extract_track(mkv, track_id, out)`. Architecture layering tests pass.

---

## Phase 3: User Story 1 — Embedded Subtitle Extraction (Priority: P1) 🎯 MVP

**Goal**: Episodes with only embedded ASS subtitles are automatically extracted via `mkvextract` using configurable language preferences, then processed through the normal repair → sync → font → mux pipeline.

**Independent Test**: Create a mock `LibraryScanResult` with `SubtitleSource.EMBEDDED` and an `EmbeddedSubInfo` containing an Arabic track. Verify the pipeline extracts the track, sets `subtitle_path`, and proceeds to `_analyze_episode()` instead of skipping.

### Implementation for User Story 1

- [ ] T008 [US1] Update `_parse_embedded_info()` to populate `EmbeddedTrack` objects with `track_id`, `language`, `language_ietf`, `is_default`, and `codec` from `mkvmerge -J` JSON in `src/core/library_scanner.py`
- [ ] T009 [US1] Add `mkvextract_adapter: MkvextractPort | None = None` parameter to `PipelineRunner.__init__()` in `src/core/pipeline_runner.py`
- [ ] T010 [US1] Implement `PipelineRunner._select_track()` method with language matching, default-preference, and strict/non-strict fallback logic in `src/core/pipeline_runner.py`
- [ ] T011 [US1] Replace the `SubtitleSource.EMBEDDED` skip block (lines 122–142) with track selection → extraction → scan rewrite logic in `PipelineRunner.run()` in `src/core/pipeline_runner.py`
- [ ] T012 [US1] Add `from datetime import timedelta` import and structlog events for extraction start/success/skip/fail in `src/core/pipeline_runner.py`

**Checkpoint**: Running the pipeline against a directory with embedded-only MKVs no longer skips them. Arabic tracks are extracted to `.anime_studio_trash/EXP-…-.tmp.ass` and processed through repair → mux. Episodes without a matching language (strict mode) are skipped with a warning in the report.

---

## Phase 4: Tests

**Purpose**: Verify all new and modified components. Tests reference the spec's acceptance scenarios and the plan's verification plan.

- [ ] T013 [P] [US1] Unit test `EmbeddedTrack` construction, `EmbeddedSubInfo` computed properties (`track_count`, `languages`), and serialization in `tests/unit/models/test_pipeline.py`
- [ ] T014 [P] [US1] Unit test `SubtitleConfig` defaults, TOML loading with `[subtitle]` section present, and TOML loading with section absent (fallback to defaults) in `tests/unit/test_config.py`
- [ ] T015 [P] [US1] Unit test `MkvextractAdapter.extract_track()` — mock `SubprocessPort`, verify args are `["mkvextract", "tracks", "<path>", "N:<out>"]`, verify success/failure propagation in `tests/unit/adapters/test_mkvextract.py`
- [ ] T016 [P] [US1] Unit test `_parse_embedded_info()` with mock `mkvmerge -J` JSON containing multiple tracks (Arabic default, English non-default, non-ASS track), verify `EmbeddedTrack` population in `tests/unit/core/test_library_scanner.py`
- [ ] T017 [P] [US1] Unit test `PipelineRunner._select_track()` — all branches: preferred match (single), multiple matches prefer default, no match strict=True→None, no match strict=False→fallback in `tests/unit/core/test_pipeline_runner.py`
- [ ] T018 [US1] Unit test `PipelineRunner.run()` embedded extraction flow — mock mkvextract adapter, verify `extract_track` called, `subtitle_path` updated, episode proceeds to `_analyze_episode` in `tests/unit/core/test_pipeline_runner.py`

**Checkpoint**: `pytest tests/unit/ -v --tb=short` passes with all new tests green. Coverage for new code ≥ 85%.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Finalize exports, fix downstream breakage, validate architecture.

- [ ] T019 [P] Update any existing tests constructing `EmbeddedSubInfo(track_count=..., languages=...)` to use new `tracks=[EmbeddedTrack(...)]` constructor in `tests/unit/`
- [ ] T020 [P] Verify architecture layering test still passes (no port/adapter boundary violations) by running `tests/unit/test_architecture_layering.py`
- [ ] T021 Run full test suite `pytest tests/unit/ -v --tb=short` and fix any regressions
- [ ] T022 Run `ruff check src/ tests/` and `ruff format --check src/ tests/` — fix any lint/format violations

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Can run in parallel with Phase 1 (different files)
- **User Story 1 (Phase 3)**: Depends on Phase 1 (config + models) and Phase 2 (port + adapter) completion
- **Tests (Phase 4)**: Depends on Phase 3 completion
- **Polish (Phase 5)**: Depends on Phase 4 completion

### Within Phase Dependencies

```text
Phase 1:  T001 ─┐
          T002 ─┤ (parallel, different files)
          T003 ─┘ (depends on T002 for EmbeddedTrack export)

Phase 2:  T004 ─┐
          T005 ─┤ (parallel, different files)
          T006 ─┘ (depends on T004 for protocol)
          T007   (depends on T006 for adapter class)

Phase 3:  T008  (depends on T002)
          T009  (depends on T004/T006)
          T010  (depends on T002, T009)
          T011  (depends on T008, T009, T010)
          T012  (part of T011, same file)

Phase 4:  T013─T017 (all parallel, different test files)
          T018 (depends on T013-T017 for consistency, same file as T017)

Phase 5:  T019─T020 (parallel)
          T021─T022 (sequential, validation)
```

### Parallel Opportunities

```bash
# Phase 1 — launch together:
Task T001: "Add SubtitleConfig to src/config.py"
Task T002: "Add EmbeddedTrack to src/models/pipeline.py"

# Phase 2 — launch together:
Task T004: "Create MkvextractPort in src/ports/mkvextract.py"
Task T005: "Export MkvextractPort from src/ports/__init__.py"

# Phase 4 — launch ALL test tasks together:
Task T013: "Test EmbeddedTrack models"
Task T014: "Test SubtitleConfig"
Task T015: "Test MkvextractAdapter"
Task T016: "Test _parse_embedded_info"
Task T017: "Test _select_track"
```

---

## Implementation Strategy

### MVP First (Phase 1–3)

1. Complete Phase 1: Config + Models (T001–T003)
2. Complete Phase 2: Port + Adapter (T004–T007)
3. Complete Phase 3: Pipeline Integration (T008–T012)
4. **STOP and VALIDATE**: Run pipeline manually against an MKV with embedded Arabic subs
5. Verify extraction → repair → mux completes successfully

### Full Delivery

1. Complete MVP (Phases 1–3)
2. Add Tests (Phase 4: T013–T018)
3. Polish (Phase 5: T019–T022)
4. Final validation: `pytest tests/unit/ -v` all green

---

## Notes

- [P] tasks = different files, no dependencies
- [US1] = the single user story: Embedded Subtitle Extraction
- `FilesystemPort.ensure_directory()` already exists — no changes needed
- `mkvextract` is already registered as CRITICAL in `DependencyChecker.DEFAULT_SPECS`
- The `mkvextract_adapter` param is optional (`None` default) for backward compatibility
- Extracted files use TrashReceipt naming: `EXP-YYYY-MM-DD-<stem>.tmp.ass`
- Commit after each task or logical group
- Stop at any checkpoint to validate independently
