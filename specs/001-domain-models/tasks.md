# Tasks: Domain Models Layer

**Input**: Design documents from `/specs/001-domain-models/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

**Tests**: Included — constitution §X mandates Test-First, spec.md defines acceptance scenarios.

**Organization**: Tasks grouped by user story. US1 (P1) COMPLETE. US2+US4 can proceed in parallel. US3 depends on US1 (done). US5 depends on US2+US3.

**Progress**: 11/30 tasks complete (Phases 1-3). Remaining: 19 tasks across Phases 4-8.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure) ✅ COMPLETE

**Purpose**: Project structure, dependencies, package initialization

- [x] T001 Create `src/models/` package directory and empty `src/models/__init__.py`
- [x] T002 Initialize project dependency — run `uv add pydantic>=2.11.0` and verify `pyproject.toml` updated
- [x] T003 [P] Create `tests/unit/models/` package directory and empty `tests/unit/models/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites) ✅ COMPLETE

**Purpose**: Shared type aliases and base patterns that ALL user story models depend on

- [x] T004 Create `SerializablePath` type alias in `src/models/_types.py` — `Annotated[Path, PlainSerializer(lambda p: p.as_posix(), return_type=str)]` per research R-002

---

## Phase 3: User Story 1 — Define Font Acquisition Data Structures (Priority: P1) ✅ COMPLETE 🎯 MVP

**Goal**: `FontQuery`, `FontAsset`, `HunterResult` models in `src/models/font.py`

- [x] T005 [P] [US1] Write unit tests for `FontQuery` in `tests/unit/models/test_font.py`
- [x] T006 [P] [US1] Write unit tests for `FontAsset` in `tests/unit/models/test_font.py`
- [x] T007 [P] [US1] Write unit tests for `HunterResult` in `tests/unit/models/test_font.py`
- [x] T008 [US1] Implement `FontQuery` model in `src/models/font.py`
- [x] T009 [US1] Implement `FontAsset` model in `src/models/font.py`
- [x] T010 [US1] Implement `HunterResult` model in `src/models/font.py`
- [x] T011 [US1] Run `pytest tests/unit/models/test_font.py -v` — all US1 tests must pass

---

## Phase 4: User Story 2 — Define Subtitle Processing Data Structures (Priority: P1)

**Goal**: `SubtitleFile` and `SyncResult` models in `src/models/subtitle.py` — encoding detection and sync operation results.

**Independent Test**: Construct models with representative data, validate constraints (`fonts_required` is list[str]), verify immutability and JSON round-trip.

### Tests for User Story 2

> **NOTE: Write tests FIRST, ensure they FAIL before implementation**

- [x] T012 [P] [US2] Write unit tests for `SubtitleFile` in `tests/unit/models/test_subtitle.py` — test construction with encoding `cp1252`, `is_repaired` default False, `fonts_required` as list[str], `path` serializes as POSIX string, frozen immutability, JSON round-trip
- [x] T013 [P] [US2] Write unit tests for `SyncResult` in `tests/unit/models/test_subtitle.py` — test with/without `tool_fallback_used` (default None), `duration_ms` ge=0 validation, frozen immutability, JSON round-trip

### Implementation for User Story 2

- [x] T014 [P] [US2] Implement `SubtitleFile` model in `src/models/subtitle.py` — fields: `path` (SerializablePath), `encoding_detected` (str), `encoding_source` (str), `line_ending` (str), `fonts_required` (list[str]), `is_repaired` (bool, default False). ConfigDict(frozen=True).
- [x] T015 [US2] Implement `SyncResult` model in `src/models/subtitle.py` — fields: `success` (bool), `tool_used` (str), `tool_fallback_used` (str|None, default None), `offset_ms` (float), `duration_ms` (float, ge=0). ConfigDict(frozen=True).
- [x] T016 [US2] Run `pytest tests/unit/models/test_subtitle.py -v` — all US2 tests must pass

**Checkpoint**: Subtitle models functional and independently testable

---

## Phase 5: User Story 3 — Define Muxing Pipeline Data Structures (Priority: P1)

**Goal**: `MuxJob` and `MuxResult` models in `src/models/mux.py` — mux operation inputs and outputs.

**Independent Test**: Construct `MuxJob` with list of `FontAsset`, verify `dry_run` defaults False, `MuxResult.warnings` defaults empty list, JSON round-trip with nested models.

**Dependency**: Imports `FontAsset` from `src/models/font.py` (US1 ✅ complete)

### Tests for User Story 3

> **NOTE: Write tests FIRST, ensure they FAIL before implementation**

- [x] T017 [P] [US3] Write unit tests for `MuxJob` in `tests/unit/models/test_mux.py` — test with 3 FontAsset instances, `dry_run` default False, empty fonts list valid, all Path fields serialize as POSIX, frozen immutability, JSON round-trip
- [x] T018 [P] [US3] Write unit tests for `MuxResult` in `tests/unit/models/test_mux.py` — test `fonts_attached` ge=0, `warnings` default empty list, `duration_ms` ge=0, `output_path` POSIX serialization, frozen immutability, JSON round-trip

### Implementation for User Story 3

- [x] T019 [P] [US3] Implement `MuxJob` model in `src/models/mux.py` — fields: `episode_path` (SerializablePath), `subtitle_path` (SerializablePath), `fonts` (list[FontAsset]), `dry_run` (bool, default False), `output_path` (SerializablePath). Import FontAsset from font.py. ConfigDict(frozen=True).
- [x] T020 [US3] Implement `MuxResult` model in `src/models/mux.py` — fields: `success` (bool), `output_path` (SerializablePath), `duration_ms` (float, ge=0), `fonts_attached` (int, ge=0), `warnings` (list[str], default []). ConfigDict(frozen=True).
- [x] T021 [US3] Run `pytest tests/unit/models/test_mux.py -v` — all US3 tests must pass

**Checkpoint**: Mux models functional, nested FontAsset serialization verified

---

## Phase 6: User Story 4 — Define Tool Execution Result (Priority: P1)

**Goal**: `ToolResult` model in `src/models/tool_result.py` — universal subprocess result envelope per Constitution Principle IV.

**Independent Test**: Create success/failure ToolResult instances, verify `suggestion` optional, JSON round-trip clean.

### Tests for User Story 4

> **NOTE: Write tests FIRST, ensure they FAIL before implementation**

- [x] T022 [P] [US4] Write unit tests for `ToolResult` in `tests/unit/models/test_tool_result.py` — test success case (exit_code=0, suggestion None), failure case (non-zero exit_code, suggestion populated), `stdout`/`stderr` default empty string, `duration_ms` ge=0, frozen immutability, JSON round-trip

### Implementation for User Story 4

- [x] T023 [P] [US4] Implement `ToolResult` model in `src/models/tool_result.py` — fields: `tool_name` (str), `success` (bool), `exit_code` (int), `stdout` (str, default ""), `stderr` (str, default ""), `duration_ms` (float, ge=0), `suggestion` (str|None, default None). ConfigDict(frozen=True).
- [x] T024 [US4] Run `pytest tests/unit/models/test_tool_result.py -v` — all US4 tests must pass

**Checkpoint**: ToolResult functional, Constitution §IV compliance verified

---

## Phase 7: User Story 5 — Define Pipeline Reporting Data Structures (Priority: P2)

**Goal**: `EpisodeStatus` enum, `EpisodeReport` and `PipelineReport` models in `src/models/report.py` — structured pipeline reporting per Constitution §X-bis.

**Independent Test**: Construct reports with mixed statuses (COMPLETE, PARTIAL, FAILED, SKIPPED), verify enum iteration, aggregation fields, JSON round-trip.

**Dependency**: Imports `SyncResult` from subtitle.py (US2) and `MuxResult` from mux.py (US3)

### Tests for User Story 5

> **NOTE: Write tests FIRST, ensure they FAIL before implementation**

- [x] T025 [P] [US5] Write unit tests for `EpisodeStatus` in `tests/unit/models/test_report.py` — test enum has exactly 4 values (COMPLETE, PARTIAL, FAILED, SKIPPED), is `StrEnum`, values are lowercase strings
- [x] T026 [P] [US5] Write unit tests for `EpisodeReport` and `PipelineReport` in `tests/unit/models/test_report.py` — test `EpisodeReport` with optional `subtitle_result`/`mux_result` (default None), `missing_fonts` default empty, `applied_rules` default empty, frozen immutability. Test `PipelineReport` with list of EpisodeReport, `genuine_misses` default empty, `run_timestamp` datetime, `total_fonts_found` ge=0, `duration_ms` ge=0, frozen immutability, JSON round-trip.

### Implementation for User Story 5

- [x] T027 [US5] Implement `EpisodeStatus` enum in `src/models/report.py` — `StrEnum` with values: COMPLETE="complete", PARTIAL="partial", FAILED="failed", SKIPPED="skipped"
- [x] T028 [US5] Implement `EpisodeReport` model in `src/models/report.py` — fields: `episode_path` (SerializablePath), `status` (EpisodeStatus), `subtitle_result` (SyncResult|None, default None), `mux_result` (MuxResult|None, default None), `missing_fonts` (list[str], default []), `applied_rules` (list[str], default []). Import SyncResult from subtitle.py, MuxResult from mux.py. ConfigDict(frozen=True).
- [x] T029 [US5] Implement `PipelineReport` model in `src/models/report.py` — fields: `run_timestamp` (datetime), `duration_ms` (float, ge=0), `anime_title` (str), `episodes` (list[EpisodeReport]), `total_fonts_found` (int, ge=0), `genuine_misses` (list[str], default []). ConfigDict(frozen=True).
- [x] T030 [US5] Run `pytest tests/unit/models/test_report.py -v` — all US5 tests must pass

**Checkpoint**: All 11 models + 1 enum complete, reporting pipeline fully defined

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Re-exports, full suite validation, documentation

- [x] T031 Populate `src/models/__init__.py` with `__all__` re-exporting all 11 public models + `EpisodeStatus` enum + `SerializablePath` type alias
- [x] T032 Run full test suite `pytest tests/unit/models/ -v` — all tests pass, zero import errors
- [x] T033 Run quickstart.md validation — execute code snippets from `specs/001-domain-models/quickstart.md` in a scratch script to confirm all examples work

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: ✅ COMPLETE
- **Foundational (Phase 2)**: ✅ COMPLETE
- **US1 Font (Phase 3)**: ✅ COMPLETE
- **US2 Subtitle (Phase 4)**: Ready to start — imports `SerializablePath` from `_types.py`
- **US3 Mux (Phase 5)**: Ready to start — imports `FontAsset` from `font.py` (US1 ✅)
- **US4 Tool (Phase 6)**: Ready to start — no cross-model dependencies
- **US5 Report (Phase 7)**: Blocked by **US2** + **US3** — imports `SyncResult`, `MuxResult`
- **Polish (Phase 8)**: Blocked by all user stories complete

### Remaining Dependency Graph

```
  ┌── US2 (Subtitle) ──────┐
  │                         ├──► US5 (Report) ──► Polish
  ├── US3 (Mux) ───────────┘
  └── US4 (Tool) ───────────────────────────────► Polish
```

- **US2, US3, US4**: All can proceed in parallel NOW
- **US5**: Starts when US2 + US3 both complete
- **Polish**: Starts when all 5 user stories complete

### Parallel Opportunities

- US2, US3, US4 can all run in parallel immediately (different files, no cross-deps)
- Within each story: tests [P] can run in parallel, then models sequentially

---

## Parallel Example: Immediate Start

```bash
# Launch these 3 stories simultaneously (different files, no cross-deps):
Worker A: US2 — tests + models in src/models/subtitle.py
Worker B: US3 — tests + models in src/models/mux.py
Worker C: US4 — tests + models in src/models/tool_result.py

# Then sequentially:
Worker A: US5 — tests + models in src/models/report.py (needs SyncResult + MuxResult)
Worker B: Polish — __init__.py re-exports, full suite
```

---

## Implementation Strategy

### Current State

Phases 1-3 complete. Font models (US1) fully implemented and tested.

### Next Steps (Incremental Delivery)

1. US2 (Subtitle) + US3 (Mux) + US4 (Tool) → parallel → Test each → ✅ 3 pipelines unblocked
2. US5 (Report) → Test → ✅ Reporting pipeline unblocked
3. Polish → `__init__.py` re-exports, full suite green, quickstart validation

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- All models use `ConfigDict(frozen=True)` — no exceptions
- All Path fields use `SerializablePath` type alias from `_types.py`
- No imports from `core/`, `adapters/`, `hunters/`, `tui/` (FR-015)
- Commit after each phase or logical group
- Task IDs T012-T033 renumbered for remaining work continuity
