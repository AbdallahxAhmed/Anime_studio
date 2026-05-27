# Tasks: Font Ingestion System

**Input**: Design documents from `/specs/007-font-ingestion/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — spec references pytest and constitution mandates 85% core coverage.

**Organization**: Tasks follow strict inner-to-outer dependency layers: Domain Models → Core Services & Hunters → Core Integrations → Presentation Layer.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Test fixtures and shared infrastructure needed by all phases

- [ ] T001 Create sample font test fixtures in tests/fixtures/fonts/ (at minimum: one valid .ttf, one valid .otf, one corrupt/zero-byte .ttf)
- [ ] T002 [P] Verify fonttools is available in dev environment by running `uv pip show fonttools`

---

## Phase 2: Foundational — Domain Models (Inner Layer)

**Purpose**: Pure data models with zero I/O. MUST complete before core services or hunters.

**⚠️ CRITICAL**: All core services, hunters, and GUI code depend on these model changes.

- [ ] T003 [P] Add `is_cacheable: bool = True` field to `FontAsset` model in src/models/font.py
- [ ] T004 [P] Create `FontIngestionResult` frozen Pydantic model in src/models/ingestion.py with fields: `success_count: int`, `skipped_count: int`, `failed_count: int`, `failed_details: list[tuple[SerializablePath, str]]`, `source: str`
- [ ] T005 [P] Add `LibraryScanOutput` frozen Pydantic model to src/models/pipeline.py with fields: `episodes: list[LibraryScanResult]`, `font_directories: list[SerializablePath] = Field(default_factory=list)`
- [ ] T006 [P] Add unit tests for `is_cacheable` field default and serialization in tests/unit/models/test_font.py
- [ ] T007 [P] Add unit tests for `FontIngestionResult` construction and frozen enforcement in tests/unit/models/test_ingestion.py
- [ ] T008 [P] Add unit tests for `LibraryScanOutput` construction in tests/unit/models/test_pipeline_models.py

**Checkpoint**: `pytest tests/unit/models/test_font.py tests/unit/models/test_ingestion.py tests/unit/models/test_pipeline_models.py` — all pass. Models frozen, serializable, no I/O.

---

## Phase 3: User Story 1 — System Font Resolution (Priority: P1) 🎯 MVP

**Goal**: Fonts installed on the user's OS are automatically discovered and resolved in-place via `SystemFontHunter` (HunterProtocol, priority 4), without network or cache copy.

**Independent Test**: Create a mock ASS referencing "Arial", run `FontResolver.resolve()`, verify SystemFontHunter returns `FontAsset(is_cacheable=False, source="system")` with absolute path.

### Tests for User Story 1

- [ ] T009 [P] [US1] Add contract test verifying `SystemFontHunter` conforms to `HunterProtocol` (runtime_checkable) in tests/contract/test_hunter_protocol.py
- [ ] T010 [P] [US1] Create unit tests for `SystemFontHunter` in tests/unit/hunters/test_system_font_hunter.py: test `_get_system_font_dirs()` per OS, test `_extract_font_names()` with fixture .ttf, test `search()` match/miss, test `supports()` always True, test `download()` raises NotImplementedError

### Implementation for User Story 1

- [ ] T011 [US1] Implement `SystemFontHunter` class in src/hunters/system_font_hunter.py: `HunterProtocol` conformant, cross-platform dir scanning via `sys.platform` + `pathlib.Path`, lazy name→path index built on first `search()` call using `fonttools` TTFont nameID extraction, `is_cacheable=False` on returned `FontAsset`, `download()` raises `NotImplementedError`
- [ ] T012 [US1] Modify `FontResolver.resolve()` in src/core/font_resolver.py: add 3-line short-circuit after `hunter.search()` — if `results[0].font_asset` has `is_cacheable=False`, record CB success and return asset directly (skip `download` + `cache.store`)
- [ ] T013 [US1] Add unit test for `FontResolver` is_cacheable short-circuit in tests/unit/core/test_font_resolver.py: mock hunter returning `FontAsset(is_cacheable=False)`, verify `download()` never called, verify `cache.store()` never called

**Checkpoint**: `pytest tests/unit/hunters/ tests/contract/ tests/unit/core/test_font_resolver.py` — all pass. SystemFontHunter resolves "Arial" on Windows, falls through on miss, no cache writes.

---

## Phase 4: User Story 2 — Auto-Discovery from Anime Library (Priority: P1)

**Goal**: Pipeline scan detects `Fonts/` dirs in the anime library, pre-ingests all .ttf/.otf into cache (O(1) per batch) before episode analysis, using `FontIngestionService`.

**Independent Test**: Create temp dir with `Fonts/CustomFont.ttf`, run `scan_library()`, verify `font_directories` populated in `LibraryScanOutput`, run `FontIngestionService.ingest_directories()`, verify font in cache.

### Tests for User Story 2

- [ ] T014 [P] [US2] Create unit tests for `FontIngestionService` in tests/unit/core/test_font_ingestion.py: test `ingest_directories()` with new fonts (success), test dedup (skipped), test corrupt font (failed), test empty dir, test mixed results (success+skipped+failed), verify structlog event emitted with correct fields
- [ ] T015 [P] [US2] Add unit tests for `scan_library()` font dir detection in tests/unit/core/test_library_scanner.py: test `Fonts/` detected, test `fonts/` detected (case-insensitive), test no-fonts-dir returns empty list, test `LibraryScanOutput` structure

### Implementation for User Story 2

- [ ] T016 [US2] Implement `FontIngestionService` class in src/core/font_ingestion.py: async stateless service, constructor takes `FontCache` + `asyncio.Semaphore`, `ingest_directories()` scans for .ttf/.otf recursively, reads bytes via `asyncio.to_thread()`, extracts nameID via fonttools, dedup via `FontCache.lookup()`, stores via `FontCache.store()`, returns `FontIngestionResult`, logs `font_ingestion_complete` event via structlog
- [ ] T017 [US2] Implement `ingest_files()` method on `FontIngestionService` in src/core/font_ingestion.py: accepts list of individual file paths, same dedup/store/report logic as `ingest_directories()`, used by drag-drop
- [ ] T018 [US2] Modify `scan_library()` in src/core/library_scanner.py: change return type from `list[LibraryScanResult]` to `LibraryScanOutput`, detect `Fonts/`/`fonts/` directories during the `_scan()` walk (case-insensitive match on dir name), deduplicate by resolved path, populate `font_directories` field
- [ ] T019 [US2] Modify `PipelineRunner.__init__()` in src/core/pipeline_runner.py: add `font_ingestion_service: FontIngestionService` and `disk_semaphore: asyncio.Semaphore` parameters, store as instance attributes, replace per-run semaphore creation in `run()` with injected `self.disk_semaphore`
- [ ] T020 [US2] Modify `PipelineRunner.run()` in src/core/pipeline_runner.py: update scan call to unpack `LibraryScanOutput` (`scan_output.episodes`, `scan_output.font_directories`), add pre-pipeline step calling `self.font_ingestion_service.ingest_directories(font_dirs, source="auto_discovery")` between scan and analysis loop
- [ ] T021 [US2] Update `PipelineRunner` unit tests in tests/unit/core/test_pipeline_runner.py: mock `scan_library()` to return `LibraryScanOutput`, mock `FontIngestionService`, verify pre-pipeline ingestion called with font_dirs before `_analyze_episode`, verify semaphore injected correctly

**Checkpoint**: `pytest tests/unit/core/test_font_ingestion.py tests/unit/core/test_library_scanner.py tests/unit/core/test_pipeline_runner.py` — all pass. Pipeline ingests Fonts/ dirs once before analysis.

---

## Phase 5: User Story 3 — Manual Font Import (Priority: P2)

**Goal**: User clicks "Import Fonts" button in MainWindow, selects folder via QFileDialog, async-ingests fonts into cache, result shown in Activity Feed.

**Independent Test**: Click "Import Fonts", select folder with sample fonts, verify Activity Feed shows "N new, M skipped, K failed".

### Implementation for User Story 3

- [ ] T022 [US3] Modify `bootstrap_app()` in src/gui/bootstrap.py: create shared `asyncio.Semaphore(config.max_concurrent_disk_io)`, instantiate `FontIngestionService(cache, disk_semaphore)`, pass both `font_ingestion_service` and `disk_semaphore` to `PipelineRunner`, pass `font_ingestion_service` to `MainWindow`
- [ ] T023 [US3] Modify `MainWindow.__init__()` in src/gui/main_window.py: accept `font_ingestion_service` parameter, add `QPushButton("Import Fonts")` in left panel config group (between `LibraryPickerWidget` and "Run Pipeline" button), connect button `clicked` signal to `_on_import_fonts_click`
- [ ] T024 [US3] Implement `_on_import_fonts_click()` as `@asyncSlot()` in src/gui/main_window.py: open `QFileDialog.getExistingDirectory()`, on selection call `await self.font_ingestion_service.ingest_directories([Path(folder)], source="manual_import")`, result emitted via structlog → SignalBridge → ActivityFeedWidget
- [ ] T025 [US3] Add unit test for Import Fonts button presence and dialog trigger in tests/unit/gui/test_main_window.py

**Checkpoint**: Manual import button visible, QFileDialog opens, ingestion runs async, Activity Feed shows results.

---

## Phase 6: User Story 4 — Drag & Drop Font Import (Priority: P2)

**Goal**: User drags folder or .ttf/.otf files onto MainWindow, drop triggers async ingestion, visual feedback during drag.

**Independent Test**: Simulate drag-drop event with font folder, verify green border on dragover, verify Activity Feed shows ingestion result.

### Implementation for User Story 4

- [ ] T026 [US4] Implement drag-and-drop on `MainWindow` in src/gui/main_window.py: call `self.setAcceptDrops(True)` in `__init__`, store `self._default_style = self.styleSheet()`, override `dragEnterEvent()` to validate MIME URLs (folders or .ttf/.otf), set green border stylesheet on valid drag, override `dragLeaveEvent()` to reset style, override `dropEvent()` to reset style and dispatch to async handler
- [ ] T027 [US4] Implement `_handle_font_drop()` async method in src/gui/main_window.py: separate paths into dirs and files, call `ingest_directories()` for dirs and `ingest_files()` for individual font files, result flows through structlog
- [ ] T028 [US4] Implement `_is_valid_font_drop(url)` helper in src/gui/main_window.py: check `url.toLocalFile()` — accept if directory or if extension in `.ttf`/`.otf` (case-insensitive)
- [ ] T029 [US4] Add unit tests for drag-drop validation and event handling in tests/unit/gui/test_main_window.py: test dragEnterEvent accepts valid drops, rejects invalid, test dropEvent dispatches correctly

**Checkpoint**: Drag folder → green border → drop → ingestion → Activity Feed result. Drag .txt → rejected.

---

## Phase 7: User Story 5 — Ingestion Feedback via Activity Feed (Priority: P1)

**Goal**: All ingestion paths (auto-discovery, manual, drag-drop) report results through SignalBridge → ActivityFeedWidget with itemized counts.

**Independent Test**: Trigger ingestion with known inputs, verify Activity Feed shows "Font ingestion complete: N new, M skipped, K failed".

> **Note**: Most feedback wiring is already done in Phases 4-6 (structlog → GuiLogBridge → SignalBridge → ActivityFeedWidget). This phase validates the end-to-end flow and ensures message formatting.

### Implementation for User Story 5

- [ ] T030 [US5] Verify structlog event `font_ingestion_complete` in `FontIngestionService` includes fields: `event`, `success_count`, `skipped_count`, `failed_count`, `source` — add/adjust if needed in src/core/font_ingestion.py
- [ ] T031 [US5] Verify `ActivityFeedWidget.add_entry()` correctly formats ingestion events in src/gui/widgets/activity_feed.py — the existing handler should display the structured log event, but verify the `font_ingestion_complete` event renders a human-readable message (e.g., "Font ingestion complete: 15 new, 3 skipped, 2 failed")
- [ ] T032 [US5] Add integration-style unit test in tests/unit/core/test_font_ingestion.py: verify structlog captures the `font_ingestion_complete` event with correct field values after ingestion

**Checkpoint**: End-to-end feedback verified for all three triggers.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Architecture validation, cleanup, and final checks

- [ ] T033 [P] Update architecture boundary test in tests/unit/test_architecture_layering.py: verify `src/hunters/system_font_hunter.py` does not import from `src/gui/`, verify `src/core/font_ingestion.py` does not import from `src/gui/` or `PySide6`
- [ ] T034 [P] Run `ruff check src/hunters/system_font_hunter.py src/core/font_ingestion.py src/models/ingestion.py` — zero warnings
- [ ] T035 [P] Run `ruff format --check src/hunters/system_font_hunter.py src/core/font_ingestion.py src/models/ingestion.py` — no formatting changes needed
- [ ] T036 Run full test suite: `pytest tests/unit/ tests/contract/` — all pass, no regressions
- [ ] T037 Run quickstart.md smoke tests (manual validation of scenarios 1-11)
- [ ] T038 Verify `mypy src/hunters/system_font_hunter.py src/core/font_ingestion.py src/models/ingestion.py --strict` — zero errors

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
    └──→ Phase 2 (Domain Models) ← BLOCKS ALL subsequent phases
              ├──→ Phase 3 (US1: SystemFontHunter) ← can start after Phase 2
              ├──→ Phase 4 (US2: Auto-Discovery + FontIngestionService) ← can start after Phase 2
              │         ├──→ Phase 5 (US3: Manual Import) ← needs FontIngestionService from Phase 4
              │         └──→ Phase 6 (US4: Drag & Drop) ← needs FontIngestionService from Phase 4
              └──→ Phase 7 (US5: Feedback) ← needs structlog events from Phase 4
                        └──→ Phase 8 (Polish) ← after all user stories
```

### User Story Dependencies

- **US1 (SystemFontHunter)**: Depends only on Phase 2 models. Independent of US2-US5.
- **US2 (Auto-Discovery)**: Depends on Phase 2 models. Independent of US1, but US3/US4 need `FontIngestionService` created here.
- **US3 (Manual Import)**: Depends on `FontIngestionService` from US2. Independent of US1, US4.
- **US4 (Drag & Drop)**: Depends on `FontIngestionService` from US2. Independent of US1, US3.
- **US5 (Feedback)**: Depends on structlog events from US2's `FontIngestionService`. Can run after US2.

### Within Each Phase

1. Tests written first (where included)
2. Domain models before services
3. Services before integrations
4. Core before GUI
5. All [P] tasks within a phase can run in parallel

### Parallel Opportunities

```
Phase 2: T003, T004, T005 run in parallel (different model files)
Phase 2: T006, T007, T008 run in parallel (different test files)
Phase 3: T009, T010 run in parallel (different test files)
Phase 5 + Phase 6: Can run in parallel (US3 + US4 both need FontIngestionService but touch different GUI code)
Phase 8: T033, T034, T035 run in parallel (different validation tools)
```

---

## Parallel Example: Phase 2 (Domain Models)

```bash
# Launch all model changes in parallel (different files):
Task T003: "Add is_cacheable to FontAsset in src/models/font.py"
Task T004: "Create FontIngestionResult in src/models/ingestion.py"
Task T005: "Add LibraryScanOutput to src/models/pipeline.py"

# Then launch all model tests in parallel:
Task T006: "Test is_cacheable in tests/unit/models/test_font.py"
Task T007: "Test FontIngestionResult in tests/unit/models/test_ingestion.py"
Task T008: "Test LibraryScanOutput in tests/unit/models/test_pipeline_models.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup (fixtures)
2. Complete Phase 2: Domain Models (all 3 model changes)
3. Complete Phase 3: SystemFontHunter (resolve system fonts in-place)
4. Complete Phase 4: FontIngestionService + Scanner + Pipeline changes
5. **STOP and VALIDATE**: Test system font resolution + auto-discovery independently
6. Run `pytest` — all tests pass, no regressions

### Full Delivery (US1 → US5)

1. Complete MVP (Phases 1-4)
2. Phase 5: Manual Import button (GUI addition)
3. Phase 6: Drag & Drop (GUI addition)
4. Phase 7: Feedback validation (end-to-end)
5. Phase 8: Polish, linting, architecture tests
6. Run full quickstart.md smoke tests

### Layer Order (User-Mandated)

1. **Inner**: Domain Models (Phase 2) — `FontAsset`, `LibraryScanOutput`, `FontIngestionResult`
2. **Middle**: Core Services + Hunters (Phases 3-4) — `SystemFontHunter`, `FontIngestionService`
3. **Middle**: Core Integrations (Phase 4) — `LibraryScanner`, `PipelineRunner`, `FontResolver`
4. **Outer**: Presentation (Phases 5-6) — `MainWindow` UI, drag-drop, signals

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently testable at its checkpoint
- Constitution compliance verified at Phase 8 (architecture boundary + ruff + mypy)
- `FontIngestionService` is the shared dependency for US3, US4, US5 — created in US2's phase
- No implementation code in this file — tasks are executable specifications
