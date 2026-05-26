# Tasks: Font System

**Input**: Design documents from `specs/003-font-system/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included — constitution §X mandates test-first discipline. Unit tests for core logic, contract tests for HunterProtocol.

**Organization**: Tasks grouped by user story. US1/US2/US3 are all P1 (co-dependent core). US4/US5 are P2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create package structure and shared foundation files

- [x] T001 Create `src/core/__init__.py` with empty module docstring
- [x] T002 [P] Create `src/hunters/__init__.py` with empty module docstring
- [x] T003 [P] Create `tests/unit/core/__init__.py`
- [x] T004 [P] Create `tests/unit/hunters/__init__.py`
- [x] T005 [P] Create `tests/contract/__init__.py`
- [x] T006 [P] Create `tests/fixtures/ass_samples/` directory with sample ASS files (valid 3-style, corrupt missing section, malformed style line, CJK font names, Arabic font names)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Error taxonomy extensions and config fields that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Add `FontMatchError`, `HunterError`, `EncodingRepairError` exception classes to `src/errors.py`
- [x] T008 Add `circuit_breaker_cooldown_s: float = 60.0`, `font_cache_path: Path | None = None`, `startup_ping_timeout_s: float = 2.0` fields to `AppConfig` in `src/config.py`
- [x] T009 [P] Add `FontPayload` model to `src/models/font.py` with fields: `font_name: str`, `font_data: bytes`, `file_extension: str`, `source: str`, `nameids: dict[int, str]`, `metadata: dict[str, str]` — frozen Pydantic model
- [x] T010 [P] Export `FontPayload` from `src/models/__init__.py`
- [x] T011 [P] Write unit tests for `FontPayload` validation in `tests/unit/models/test_font.py` (add new test class, don't overwrite existing tests) — test frozen, min_length, bytes field
- [x] T012 [P] Write unit tests for new error classes in `tests/unit/test_errors.py` — verify inheritance from `AnimeStudioError`
- [x] T013 [P] Write unit tests for new `AppConfig` fields in `tests/unit/test_config.py` — verify defaults, type validation, TOML loading

**Checkpoint**: Foundation ready — all new models, errors, and config fields available for user stories

---

## Phase 3: User Story 1 — Font Cache Lookup and Population (Priority: P1) 🎯 MVP

**Goal**: Persistent on-disk font cache with TOML index, version validation, lookup, and atomic write-back

**Independent Test**: Create a temp `font_cache/` dir with `font_library.toml`, query for known/unknown fonts, verify hit/miss and index integrity

### Tests for User Story 1

- [x] T014 [P] [US1] Write unit tests for `FontCache.lookup()` in `tests/unit/core/test_font_cache.py` — cache hit returns `FontAsset`, cache miss returns `None`
- [x] T015 [P] [US1] Write unit tests for `FontCache.store()` in `tests/unit/core/test_font_cache.py` — atomic write, TOML index update, `cache_version` preserved
- [x] T016 [P] [US1] Write unit tests for cache version validation in `tests/unit/core/test_font_cache.py` — stale version triggers rebuild, matching version loads normally
- [x] T017 [P] [US1] Write unit tests for cache rebuild from directory scan in `tests/unit/core/test_font_cache.py` — corrupted TOML triggers full rescan

### Implementation for User Story 1

- [x] T018 [US1] Implement `FontCache` class in `src/core/font_cache.py` with `__init__(cache_dir: Path)`, `lookup(font_name: str) -> FontAsset | None`, `store(payload: FontPayload, layer_found: int) -> FontAsset`, `_load_index() -> dict`, `_save_index(index: dict) -> None`, `_rebuild_from_scan() -> dict`
- [x] T019 [US1] Implement cache version validation in `FontCache._load_index()` — check `cache_version` against `CACHE_VERSION = "3.0"` constant, delete + rebuild on mismatch
- [x] T020 [US1] Implement atomic write in `FontCache.store()` — write font bytes to temp file, rename to final path, update TOML index atomically
- [x] T021 [US1] Add `CACHE_VERSION = "3.0"` constant to `src/config.py`
- [x] T022 [US1] Add structlog logging to `FontCache` — INFO for cache hit/miss, WARNING for version mismatch rebuild, DEBUG for index load/save

**Checkpoint**: FontCache independently functional — can store and retrieve fonts with version-safe TOML index

---

## Phase 4: User Story 3 — Circuit Breaker State Machine (Priority: P1)

**Goal**: In-memory circuit breaker with CLOSED/OPEN/HALF_OPEN states, threshold-based tripping, cooldown-based recovery

**Independent Test**: Simulate sequential failures, verify state transitions, verify `can_execute()` behavior in each state

### Tests for User Story 3

- [x] T023 [P] [US3] Write unit tests for `CircuitBreaker` state transitions in `tests/unit/core/test_circuit_breaker.py` — CLOSED→OPEN on threshold failures, OPEN→HALF_OPEN after cooldown, HALF_OPEN→CLOSED on success, HALF_OPEN→OPEN on failure
- [x] T024 [P] [US3] Write unit tests for `CircuitBreaker.can_execute()` in `tests/unit/core/test_circuit_breaker.py` — returns `True` when CLOSED, `False` when OPEN (before cooldown), `True` when OPEN (after cooldown, transitions to HALF_OPEN)
- [x] T025 [P] [US3] Write unit tests for `CircuitBreaker.record_success()` and `record_failure()` in `tests/unit/core/test_circuit_breaker.py` — verify failure count increment, threshold check, success reset

### Implementation for User Story 3

- [x] T026 [US3] Implement `CircuitBreakerState` enum (`CLOSED`, `OPEN`, `HALF_OPEN`) as `StrEnum` in `src/core/circuit_breaker.py`
- [x] T027 [US3] Implement `CircuitBreaker` class in `src/core/circuit_breaker.py` with `__init__(hunter_name: str, threshold: int, cooldown_s: float)`, `can_execute() -> bool`, `record_success() -> None`, `record_failure() -> None`, `state` property — use `match` statement for state transitions, `time.monotonic()` for cooldown tracking
- [x] T028 [US3] Add structlog logging to `CircuitBreaker` — INFO for CLOSED→OPEN and HALF_OPEN→CLOSED, DEBUG for OPEN→HALF_OPEN, WARNING for fast-fail skip

**Checkpoint**: CircuitBreaker independently functional — state machine operates correctly without any hunter dependency

---

## Phase 5: User Story 4 — Strictly Typed HunterProtocol (Priority: P2)

**Goal**: `typing.Protocol` with `@runtime_checkable` defining the contract for font acquisition sources

**Independent Test**: Create conforming and non-conforming mock classes, verify `isinstance()` and `mypy --strict` behavior

### Tests for User Story 4

- [x] T029 [P] [US4] Write contract tests in `tests/contract/test_hunter_protocol.py` — conforming class passes `isinstance(hunter, HunterProtocol)`, non-conforming class (missing method) fails `isinstance()`, verify all required attributes (`name`, `priority`, `rate_limit`, `circuit_breaker_threshold`, `ping_url`)
- [x] T030 [P] [US4] Write unit tests for protocol attribute types in `tests/contract/test_hunter_protocol.py` — verify `name` is `str`, `priority` is `int`, `rate_limit` is `float`, `circuit_breaker_threshold` is `int`, `ping_url` is `str | None`

### Implementation for User Story 4

- [x] T031 [US4] Implement `HunterProtocol` as `typing.Protocol` with `@runtime_checkable` in `src/ports/font_hunter.py` — properties: `name: str`, `priority: int`, `rate_limit: float`, `circuit_breaker_threshold: int`, `ping_url: str | None`; methods: `supports(query: FontQuery) -> bool`, `async search(query: FontQuery) -> list[HunterResult]`, `async download(result: HunterResult) -> FontPayload`
- [x] T032 [US4] Export `HunterProtocol` from `src/ports/__init__.py`

**Checkpoint**: HunterProtocol defined — all future hunter implementations can be type-checked at dev time and runtime

---

## Phase 6: User Story 2 — Hunter Registry with 6-Layer Fallback (Priority: P1)

**Goal**: Registry orchestrating priority-ordered hunter iteration with circuit breaker awareness, startup ping, and full resolution chain

**Independent Test**: Register mock hunters with controlled success/failure, verify priority ordering, circuit breaker skip, and first-success-wins behavior

### Tests for User Story 2

- [x] T033 [P] [US2] Write unit tests for `HunterRegistry.register()` in `tests/unit/hunters/test_registry.py` — register valid hunter, reject non-conforming object via `isinstance()` check, reject duplicate names
- [x] T034 [P] [US2] Write unit tests for `HunterRegistry.iter_hunters()` priority ordering in `tests/unit/hunters/test_registry.py` — hunters returned in ascending priority order
- [x] T035 [P] [US2] Write unit tests for circuit breaker integration in `tests/unit/hunters/test_registry.py` — registry skips hunters with OPEN circuit, logs WARNING

### Implementation for User Story 2

- [x] T036 [US2] Implement `HunterRegistry` class in `src/hunters/registry.py` with `register(hunter: HunterProtocol) -> None` (validates via `isinstance()`, rejects duplicates), `iter_hunters() -> Iterator[HunterProtocol]` (priority-ordered), `get_circuit(hunter_name: str) -> CircuitBreaker`
- [x] T037 [US2] Implement `FontResolver` class in `src/core/font_resolver.py` with `__init__(registry: HunterRegistry, config: AppConfig)`, `async resolve(query: FontQuery) -> FontAsset` — iterates registry, checks `supports()`, checks circuit breaker, calls `search()` then `download()`, writes to cache on success, raises `FontMatchError` with audit trail on full exhaustion
- [x] T038 [US2] Implement `async startup_ping()` method on `FontResolver` — fire concurrent HEAD requests via `asyncio.TaskGroup` for all hunters with `ping_url`, 2s timeout per ping, open circuit on failure
- [x] T039 [US2] Implement rate limiting in `FontResolver` — async-compatible per-hunter throttle respecting `rate_limit` field (simple `asyncio.sleep` between requests)
- [x] T040 [US2] Add structlog logging to `HunterRegistry` and `FontResolver` — INFO for hunter registration, resolution start/complete, cache write-back; WARNING for circuit skip, hunter failure; DEBUG for supports() check, ping result
- [x] T041 [P] [US2] Write unit tests for `FontResolver.resolve()` in `tests/unit/core/test_font_resolver.py` — Layer 1 miss + Layer 2 hit skips Layers 3-6; all layers fail raises `FontMatchError` with audit trail; circuit-broken hunter skipped
- [x] T042 [P] [US2] Write unit tests for `FontResolver.startup_ping()` in `tests/unit/core/test_font_resolver.py` — successful ping keeps CLOSED, failed ping opens circuit, completes within timeout

**Checkpoint**: Full 6-layer resolution operational — fonts resolved through cache → hunters → fuzzy match with circuit breaker protection

---

## Phase 7: User Story 5 — Subtitle Font Extraction and Repair (Priority: P2)

**Goal**: Extract font references from ASS `[V4+ Styles]` section, normalize names, deduplicate into `FontQuery` objects, repair malformed files

**Independent Test**: Parse sample ASS files and verify extracted font list matches expectations

### Tests for User Story 5

- [x] T043 [P] [US5] Write unit tests for `extract_fonts()` in `tests/unit/core/test_subtitle_repair.py` — valid ASS with 3 unique fonts produces 3 `FontQuery` objects; duplicate fonts deduplicated; empty styles section produces empty list
- [x] T044 [P] [US5] Write unit tests for font name normalization in `tests/unit/core/test_subtitle_repair.py` — "Arial Bold" → "Arial", "Noto Sans CJK JP" preserved, "@FontName" vertical prefix stripped
- [x] T045 [P] [US5] Write unit tests for `repair_ass()` in `tests/unit/core/test_subtitle_repair.py` — missing `[V4+ Styles]` raises `EncodingRepairError`, malformed style line skipped with WARNING, valid file returned unchanged

### Implementation for User Story 5

- [x] T046 [US5] Implement `repair_ass(path: Path) -> str` function in `src/core/subtitle_repair.py` — read ASS file with `encoding="utf-8"`, validate section structure, skip malformed style lines with WARNING log, raise `EncodingRepairError` for unrecoverable issues, return repaired content as string
- [x] T047 [US5] Implement `extract_fonts(content: str, episode_path: Path, anime_title: str) -> list[FontQuery]` function in `src/core/subtitle_repair.py` — parse `[V4+ Styles]` section, extract `Fontname` field (index 1 in comma-separated Format line), normalize names (strip weight suffixes, handle `@` vertical prefix), deduplicate, return `FontQuery` list
- [x] T048 [US5] Implement font name normalization helper `_normalize_font_name(raw_name: str) -> str` in `src/core/subtitle_repair.py` — strip leading/trailing whitespace, remove `@` vertical prefix, strip common weight suffixes (`Bold`, `Italic`, `Light`, `Regular`, `SemiBold`, `ExtraBold`, `Medium`, `Thin`, `Black`, `Heavy`)
- [x] T049 [US5] Add structlog logging to subtitle repair — INFO for extraction summary (N fonts found from M styles), WARNING for skipped malformed lines, DEBUG for normalization details

**Checkpoint**: Subtitle font extraction complete — ASS files can be parsed to produce `FontQuery` list for resolution pipeline

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, cleanup, and validation

- [x] T050 [P] Export `CircuitBreaker`, `CircuitBreakerState` from `src/core/__init__.py`
- [x] T051 [P] Export `FontCache` from `src/core/__init__.py`
- [x] T052 [P] Export `FontResolver` from `src/core/__init__.py`
- [x] T053 [P] Export `extract_fonts`, `repair_ass` from `src/core/__init__.py`
- [x] T054 [P] Export `HunterRegistry` from `src/hunters/__init__.py`
- [x] T055 Run `ruff check src/core/ src/hunters/ src/ports/font_hunter.py src/models/font.py` — zero warnings
- [x] T056 Run `ruff format --check src/core/ src/hunters/ src/ports/font_hunter.py src/models/font.py` — zero changes
- [x] T057 Run `pytest tests/unit/core/ tests/unit/hunters/ tests/contract/ -v` — 100% pass
- [x] T058 Validate quickstart.md examples against actual API signatures

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 - Font Cache (Phase 3)**: Depends on Phase 2 (needs `FontPayload`, `CACHE_VERSION`)
- **US3 - Circuit Breaker (Phase 4)**: Depends on Phase 2 (needs `AppConfig.circuit_breaker_cooldown_s`)
- **US4 - HunterProtocol (Phase 5)**: Depends on Phase 2 (needs `FontPayload`, `HunterResult`)
- **US2 - Hunter Registry (Phase 6)**: Depends on Phase 3 (FontCache), Phase 4 (CircuitBreaker), Phase 5 (HunterProtocol)
- **US5 - Subtitle Repair (Phase 7)**: Depends on Phase 2 (needs `FontQuery`, `EncodingRepairError`)
- **Polish (Phase 8)**: Depends on all user stories

### User Story Dependencies

- **US1 (Font Cache)**: Independent after Phase 2
- **US3 (Circuit Breaker)**: Independent after Phase 2
- **US4 (HunterProtocol)**: Independent after Phase 2
- **US5 (Subtitle Repair)**: Independent after Phase 2
- **US2 (Hunter Registry + Resolver)**: Depends on US1, US3, US4 (consumes FontCache, CircuitBreaker, HunterProtocol)

### Within Each User Story

- Tests written FIRST (must fail before implementation)
- Models/enums before services
- Services before orchestrators
- Logging added after core logic verified

### Parallel Opportunities

- Phase 1: T002-T006 all parallelizable
- Phase 2: T009-T013 all parallelizable (different files)
- After Phase 2: US1 (Phase 3), US3 (Phase 4), US4 (Phase 5), US5 (Phase 7) can ALL run in parallel
- Within US1: T014-T017 (tests) parallelizable
- Within US3: T023-T025 (tests) parallelizable
- Within US4: T029-T030 (tests) parallelizable
- Within US5: T043-T045 (tests) parallelizable

---

## Parallel Example: After Phase 2

```bash
# All four independent user stories launch simultaneously:
Stream A (US1): T014 → T015 → T016 → T017 → T018 → T019 → T020 → T021 → T022
Stream B (US3): T023 → T024 → T025 → T026 → T027 → T028
Stream C (US4): T029 → T030 → T031 → T032
Stream D (US5): T043 → T044 → T045 → T046 → T047 → T048 → T049

# After all four complete:
Stream E (US2): T033 → T034 → T035 → T036 → T037 → T038 → T039 → T040 → T041 → T042
```

---

## Implementation Strategy

### MVP First (US1 + US3 + US4)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: Font Cache (US1) — standalone cache works
4. Complete Phase 4: Circuit Breaker (US3) — standalone state machine works
5. Complete Phase 5: HunterProtocol (US4) — contract defined
6. **STOP and VALIDATE**: All three independently testable
7. Complete Phase 6: Hunter Registry (US2) — full resolution chain operational

### Incremental Delivery

1. Setup + Foundational → Base ready
2. US1 + US3 + US4 (parallel) → Core components ready
3. US2 (depends on US1+US3+US4) → Full resolution operational
4. US5 (independent) → ASS font extraction integrated
5. Polish → All exports, linting, formatting validated

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US2 (HunterRegistry + FontResolver) deliberately placed AFTER US1/US3/US4 because it integrates all three
- Phase 4 covers US3 (not US2) because Circuit Breaker must exist before Registry can use it
- Phase 6 covers US2 (not US5) because Registry is the integration point for US1+US3+US4
- All `src/core/` functions are stateless async — mocked adapters only at I/O boundaries
- `font_library.toml` writing uses `tomli_w` or manual TOML serialization (tomllib is read-only)
