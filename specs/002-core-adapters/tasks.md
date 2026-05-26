# Tasks: Core Adapters Layer

**Input**: Design documents from `specs/002-core-adapters/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Unit tests included — constitution §X mandates test coverage for adapters.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create package structure and shared dependencies

- [x] T001 Create `src/ports/` package with `src/ports/__init__.py`
- [x] T002 [P] Create `src/adapters/` package with `src/adapters/__init__.py`
- [x] T003 [P] Create `src/errors.py` with error taxonomy: `AnimeStudioError` base, `ToolNotFoundError`, `ToolExecutionError`, `ConfigurationError`
- [x] T004 [P] Create `src/config.py` with `AppConfig(BaseSettings)` — fields: `proxy`, `max_concurrent_disk_io`, `default_timeout_s`, `mux_timeout_s`, `trash_max_age_days`
- [x] T005 [P] Create `tests/unit/adapters/__init__.py` and `tests/unit/ports/__init__.py`
- [x] T006 [P] Create `tests/integration/adapters/__init__.py`

---

## Phase 2: Foundational (Port Definitions — Blocking Prerequisites)

**Purpose**: Define port protocols that ALL adapter implementations depend on

**⚠️ CRITICAL**: No adapter implementation can begin until ports are defined

- [x] T007 [P] Define `SubprocessPort` protocol in `src/ports/subprocess.py` — `execute()` method returning `ToolResult`, `@runtime_checkable`, imports only from `src/models/` and stdlib
- [x] T008 [P] Define `HttpClientPort` protocol in `src/ports/http_client.py` — `create_client()` method returning `httpx.AsyncClient`, `@runtime_checkable`, imports only from `src/models/` and stdlib
- [x] T009 Write protocol compliance tests in `tests/unit/ports/test_protocols.py` — verify `runtime_checkable` works, mock implementations satisfy protocols, import validation

**Checkpoint**: Port protocols defined — adapter implementations can now begin

---

## Phase 3: User Story 4 - Port Interface Definitions (Priority: P1) 🎯

**Goal**: Validate port protocols are syntactically correct, runtime-checkable, and import-compliant

**Independent Test**: Protocols pass `isinstance()` checks with mock implementations; no imports from forbidden packages

*Note: US4 implementation is covered by Phase 2 tasks (T007-T009). This phase adds validation.*

- [x] T010 [US4] Add import validation test in `tests/unit/ports/test_protocols.py` — verify `src/ports/subprocess.py` and `src/ports/http_client.py` import only from `src/models/`, stdlib, `typing`, and `httpx` (type hint only)

**Checkpoint**: Port protocols fully validated and ready for adapter implementation

---

## Phase 4: User Story 1 - Tool Discovery & Binary Classification (Priority: P1)

**Goal**: Implement `DependencyChecker` with 5-step Windows-first discovery, `BinarySpec`, `ResolvedTool`, `ToolRegistry`

**Independent Test**: Mock filesystem and `shutil.which()` to verify all discovery steps, CRITICAL/OPTIONAL classification, and aggregate error reporting

### Tests for User Story 1

- [x] T011 [P] [US1] Write unit tests in `tests/unit/adapters/test_dependency_checker.py` — test 5-step discovery order, CRITICAL raises `ToolNotFoundError`, OPTIONAL logs WARNING, aggregate error for multiple missing, platform gating, executable validation

### Implementation for User Story 1

- [x] T012 [US1] Implement `BinaryClassification` enum, `BinarySpec` model, `ResolvedTool` model in `src/adapters/dependency_checker.py`
- [x] T013 [US1] Implement `ToolRegistry` container class in `src/adapters/dependency_checker.py` — `get()`, `is_available()`, `all_tools()` methods
- [x] T014 [US1] Implement `DependencyChecker` with `discover_one()` method in `src/adapters/dependency_checker.py` — 5-step search order, platform gating, executable validation
- [x] T015 [US1] Implement `DependencyChecker.discover_all()` in `src/adapters/dependency_checker.py` — iterate all known binaries, aggregate CRITICAL errors, log OPTIONAL warnings
- [x] T016 [US1] Add import validation: verify `src/adapters/dependency_checker.py` imports only from `src/models/`, `src/ports/`, `src/errors.py`, `src/config.py`, and stdlib

**Checkpoint**: Tool discovery fully functional — `DependencyChecker` finds/reports all binaries

---

## Phase 5: User Story 2 - Async Subprocess Execution Port (Priority: P1)

**Goal**: Implement `SubprocessAdapter` that executes commands via `asyncio.create_subprocess_exec()` and returns `ToolResult`

**Independent Test**: Run real processes (`echo`, `python -c`) through adapter, verify `ToolResult` fields, timeout behavior, and error handling

### Tests for User Story 2

- [x] T017 [P] [US2] Write unit tests in `tests/unit/adapters/test_subprocess.py` — test successful execution, non-zero exit code, timeout enforcement, binary not found, stderr capture, duration measurement, no raw tracebacks
- [x] T018 [P] [US2] Write integration test in `tests/integration/adapters/test_subprocess_integration.py` with `@pytest.mark.integration` — test real `echo` or `python -c` command execution

### Implementation for User Story 2

- [x] T019 [US2] Implement `SubprocessAdapter` class in `src/adapters/subprocess.py` — constructor, `execute()` method using `asyncio.create_subprocess_exec()`, implements `SubprocessPort`
- [x] T020 [US2] Add timeout enforcement in `SubprocessAdapter.execute()` — `asyncio.wait_for()`, process kill on timeout, `ToolResult(success=False, suggestion="timed out")`
- [x] T021 [US2] Add error handling in `SubprocessAdapter.execute()` — catch `FileNotFoundError`, `OSError`, `asyncio.TimeoutError`, convert all to `ToolResult(success=False)`, decode with `errors="replace"`
- [x] T022 [US2] Add duration measurement — `time.perf_counter()` start/end, populate `ToolResult.duration_ms`
- [x] T023 [US2] Add import validation: verify `src/adapters/subprocess.py` imports only from `src/models/`, `src/ports/`, `src/errors.py`, and stdlib

**Checkpoint**: Subprocess execution fully functional — all commands return `ToolResult`, no raw tracebacks

---

## Phase 6: User Story 3 - HTTP Client Port with Proxy Support (Priority: P2)

**Goal**: Implement `HttpClientAdapter` that creates `httpx.AsyncClient` with proxy from config, timeouts, and retry policy

**Independent Test**: Verify proxy config reading, client creation, timeout application, malformed proxy rejection — all mockable without network

### Tests for User Story 3

- [x] T024 [P] [US3] Write unit tests in `tests/unit/adapters/test_http_client.py` — test proxy from config, no proxy, malformed proxy raises `ConfigurationError`, timeout application, client creation

### Implementation for User Story 3

- [x] T025 [US3] Implement `HttpClientAdapter` class in `src/adapters/http_client.py` — constructor accepting proxy URL, `create_client()` method, implements `HttpClientPort`
- [x] T026 [US3] Add proxy validation in `HttpClientAdapter.__init__()` — validate proxy URL format, raise `ConfigurationError` for malformed URLs
- [x] T027 [US3] Add retry transport configuration — configure `httpx` retry for transient 5xx and connection errors
- [x] T028 [US3] Add import validation: verify `src/adapters/http_client.py` imports only from `src/models/`, `src/ports/`, `src/errors.py`, `src/config.py`, `httpx`, and stdlib

**Checkpoint**: HTTP client fully functional — proxy-aware, timeout-configured, retry-enabled

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, re-exports, and documentation

- [x] T029 [P] Update `src/ports/__init__.py` with re-exports: `SubprocessPort`, `HttpClientPort`
- [x] T030 [P] Update `src/adapters/__init__.py` with re-exports: `DependencyChecker`, `SubprocessAdapter`, `HttpClientAdapter`, `ToolRegistry`
- [x] T031 Run strict layering validation: automated import check that no file in `src/adapters/` or `src/ports/` imports from `src/core/`, `src/hunters/`, `src/tui/`
- [x] T032 Run `ruff check src/ports/ src/adapters/ src/config.py src/errors.py` — zero warnings
- [x] T033 Run `ruff format --check src/ports/ src/adapters/ src/config.py src/errors.py` — formatting pass
- [x] T034 Run full test suite: `pytest tests/unit/adapters/ tests/unit/ports/ -v` — 100% pass
- [x] T035 Run quickstart.md validation scenarios manually

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (needs packages and error taxonomy)
- **US4 Validation (Phase 3)**: Depends on Phase 2 (port protocols)
- **US1 (Phase 4)**: Depends on Phase 2 (needs `src/errors.py`, `src/config.py`)
- **US2 (Phase 5)**: Depends on Phase 2 (needs `SubprocessPort` protocol)
- **US3 (Phase 6)**: Depends on Phase 2 (needs `HttpClientPort` protocol)
- **Polish (Phase 7)**: Depends on Phases 4, 5, 6

### User Story Dependencies

- **US4 (Port Definitions)**: Foundation — MUST complete first
- **US1 (Tool Discovery)**: Depends on US4 ports + config + errors. Independent of US2, US3.
- **US2 (Subprocess Port)**: Depends on US4 ports. Independent of US1, US3.
- **US3 (HTTP Client Port)**: Depends on US4 ports + config. Independent of US1, US2.

### Within Each User Story

- Tests written and verified to FAIL before implementation
- Models/enums before logic
- Core implementation before error handling polish
- Import validation after implementation complete

### Parallel Opportunities

- T001-T006 (Setup): All [P] tasks run in parallel
- T007-T008 (Ports): Both protocols defined in parallel
- T011, T017, T024 (Tests): All test files can be written in parallel once ports exist
- US1, US2, US3 (Phases 4-6): All three user stories can run in parallel after Phase 2

---

## Parallel Example: After Phase 2

```bash
# All three user stories can launch in parallel:
Story US1: "Tool Discovery — DependencyChecker in src/adapters/dependency_checker.py"
Story US2: "Subprocess Port — SubprocessAdapter in src/adapters/subprocess.py"
Story US3: "HTTP Client — HttpClientAdapter in src/adapters/http_client.py"
```

---

## Implementation Strategy

### MVP First (US4 + US1 + US2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Port protocols (CRITICAL — blocks all stories)
3. Complete Phase 3: US4 validation
4. Complete Phase 4: US1 Tool Discovery
5. Complete Phase 5: US2 Subprocess Port
6. **STOP and VALIDATE**: Tool discovery + subprocess execution functional
7. Complete Phase 6: US3 HTTP Client
8. Complete Phase 7: Polish

### Incremental Delivery

1. Setup + Ports → Foundation ready
2. Add US1 (Tool Discovery) → Test independently → Binaries discovered
3. Add US2 (Subprocess) → Test independently → Commands execute with ToolResult
4. Add US3 (HTTP Client) → Test independently → Network ready for hunters
5. Polish → Full layer complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Each story independently completable and testable
- Commit after each task or logical group
- Import validation tasks (T016, T023, T028, T031) enforce strict layering
- Avoid: importing from `src/core/`, `src/hunters/`, `src/tui/` in any adapter or port
