# Implementation Plan: Core Adapters Layer

**Branch**: `002-core-adapters` | **Date**: 2026-05-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-core-adapters/spec.md`

## Summary

Build the foundational infrastructure adapters for Anime Studio v3 — tool binary discovery with Windows-first 5-step search order, async subprocess execution port returning `ToolResult`, HTTPX port with proxy config, error taxonomy, and application config. Strict hexagonal layering: `src/adapters/` imports only from `src/models/` and `src/ports/`.

## Technical Context

**Language/Version**: Python 3.11+ (constitution §XI — `match`, `StrEnum`, `TaskGroup`)

**Primary Dependencies**: Pydantic v2 (`>=2.11.0`), httpx (`>=0.28.0`) — both approved in constitution §XI

**Storage**: `%APPDATA%\AnimeStudio\config.toml` for settings (constitution §XIII)

**Testing**: pytest + pytest-asyncio (constitution §X). Unit tests with mocked binaries, integration tests with `@pytest.mark.integration`.

**Target Platform**: Windows-first, cross-platform (constitution §II)

**Project Type**: Library sub-package of CLI/TUI application

**Performance Goals**: Tool discovery < 500ms for all binaries combined

**Constraints**: `src/adapters/` MUST ONLY import from `src/models/`, `src/ports/`, stdlib. `src/ports/` MUST ONLY import from `src/models/`, stdlib, `typing`.

**Scale/Scope**: 7 files across 3 packages (`ports/`, `adapters/`, root config/errors) + unit tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Hexagonal Architecture** | ✅ PASS | Ports in `src/ports/`, adapters in `src/adapters/`. Adapters implement port protocols. |
| **II. Cross-Platform** | ✅ PASS | `pathlib.Path` everywhere. Windows-specific discovery gated behind `sys.platform == "win32"`. `shutil.which()` as universal fallback. |
| **III. Async-First I/O** | ✅ PASS | `asyncio.create_subprocess_exec()` for subprocess. `httpx.AsyncClient` for HTTP. `disk_io_semaphore` for bulk ops. Proxy from config.toml. |
| **IV. Structured Errors** | ✅ PASS | `ToolResult` returned from all subprocess calls. `ToolNotFoundError`, `ToolExecutionError`, `ConfigurationError` in `src/errors.py`. No raw tracebacks. |
| **V. Plugin Registry** | ✅ N/A | Hunter registry is separate feature. `ToolRegistry` is a simple container, not a plugin system. |
| **VI. Data Safety** | ✅ N/A | No file mutations in this layer. `trash_max_age_days` config field defined for future use. |
| **VII. Subprocess Lifecycle** | ✅ PASS | Timeout enforcement, process kill on timeout, stderr capture, `ToolResult` wrapping. |
| **VIII. Encoding Guarantees** | ✅ PASS | Subprocess stdout/stderr decoded with `errors="replace"`. |
| **IX. Observability** | ✅ PASS | `structlog` logging in `DependencyChecker` (tool found/missing) and `SubprocessAdapter` (command, duration, exit code). |
| **X-bis. Pipeline Report** | ✅ N/A | Report generation is core/pipeline concern. |
| **X. Test-First** | ✅ PASS | Unit tests for all components. Integration tests behind `@pytest.mark.integration`. |
| **XI. Dependency Isolation** | ✅ PASS | Only `pydantic`, `httpx`, `structlog` imported (all approved). |
| **XII. Simplicity/YAGNI** | ✅ PASS | Minimal config fields. No premature abstractions. `DependencyChecker` is concrete (single impl). Ports only for subprocess/HTTP (multiple future impls). |
| **XIII. Distribution** | ✅ PASS | 5-step discovery order implemented. Binary classification enforced. |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/002-core-adapters/
├── plan.md              # This file
├── research.md          # Phase 0 output — design decisions
├── data-model.md        # Phase 1 output — entity definitions
├── quickstart.md        # Phase 1 output — usage examples
├── contracts/           # Phase 1 output — port contracts
│   └── ports.md
└── tasks.md             # Phase 2 output (via /speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── config.py            # [NEW] Pydantic BaseSettings — AppConfig
├── errors.py            # [NEW] Error taxonomy — AnimeStudioError hierarchy
├── ports/               # [NEW] Abstract interfaces
│   ├── __init__.py
│   ├── subprocess.py    # SubprocessPort protocol
│   └── http_client.py   # HttpClientPort protocol
├── adapters/            # [NEW] I/O implementations
│   ├── __init__.py
│   ├── dependency_checker.py  # DependencyChecker + BinarySpec + ToolRegistry
│   ├── subprocess.py          # SubprocessAdapter (implements SubprocessPort)
│   └── http_client.py         # HttpClientAdapter (implements HttpClientPort)
└── models/              # [EXISTING] Domain models from 001
    ├── tool_result.py   # ToolResult (consumed by adapters)
    └── ...

tests/
├── unit/
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── test_dependency_checker.py
│   │   ├── test_subprocess.py
│   │   └── test_http_client.py
│   └── ports/
│       ├── __init__.py
│       └── test_protocols.py
└── integration/
    └── adapters/
        ├── __init__.py
        ├── test_subprocess_integration.py
        └── test_dependency_checker_integration.py
```

**Structure Decision**: Follows constitution file organization. Ports as separate package with protocol definitions. Adapters as separate package implementing ports. Config and errors at `src/` root level.

## Key Design Decisions

| Decision | Rationale | Research Ref |
|----------|-----------|--------------|
| 5-step discovery with platform gate | Constitution §XIII mandate. Scoop + mpv-config coverage. | R-001 |
| Aggregate CRITICAL error reporting | Better UX — user fixes all missing tools in one pass | R-002 |
| Single `execute()` method on SubprocessPort | YAGNI — one method covers all tools. Tool-specific logic in adapters. | R-003 |
| `create_client()` factory on HttpClientPort | Caller manages lifecycle. Simpler than wrapping every HTTP method. | R-004 |
| Partial error taxonomy | Only define errors needed now. Extend in later features. | R-005 |
| Minimal `AppConfig` | Only fields consumed by this layer. Incremental growth. | R-006 |

## Complexity Tracking

> No violations — table empty.
