# Implementation Plan: Font System

**Branch**: `003-font-system` | **Date**: 2026-05-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-font-system/spec.md`

## Summary

Build the font resolution core for Anime Studio v3 — a persistent `FontCache` with TOML index and version validation, a `HunterRegistry` orchestrating a 6-layer fallback chain (Cache → MKV Extract → Sibling Scan → System Fonts → Network Hunters → Fuzzy Match), an in-memory `CircuitBreaker` state machine (CLOSED/OPEN/HALF_OPEN) with startup fast-fail ping, a strictly typed `HunterProtocol`, and ASS `SubtitleRepair` for font extraction. All core logic lives in `src/core/`, ports in `src/ports/`, new models in `src/models/`.

## Technical Context

**Language/Version**: Python 3.11+ (constitution §XI — `match`, `StrEnum`, `TaskGroup`)

**Primary Dependencies**: Pydantic v2 (`>=2.11.0`), httpx (`>=0.28.0`), fontTools (`>=4.50.0`), structlog — all approved in constitution §XI

**Storage**: `D:\Entertainment\.anime_studio\font_cache\` + `font_library.toml` (constitution §XIII). `%APPDATA%\AnimeStudio\config.toml` for circuit breaker cooldown config.

**Testing**: pytest + pytest-asyncio (constitution §X). Unit tests with mocked hunters/filesystem. Contract tests for HunterProtocol.

**Target Platform**: Windows-first, cross-platform (constitution §II)

**Project Type**: Core library sub-package of CLI/TUI application

**Performance Goals**: Cache lookup <50ms for 500+ fonts. Startup ping ≤2s total. Full 6-layer resolution <5s per font (network hunters permitting).

**Constraints**: `src/core/` MUST NOT import from adapters/TUI/hunters. `src/ports/` MUST ONLY import from `src/models/`, stdlib, `typing`. Circuit breaker is in-memory only — no persistence. `font_library.toml` uses `CACHE_VERSION = "3.0"`.

**Scale/Scope**: ~10 files across 4 packages (`models/`, `ports/`, `core/`, `hunters/`) + unit/contract tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Hexagonal Architecture** | ✅ PASS | CircuitBreaker in `src/core/` (business logic). HunterProtocol in `src/ports/`. HunterRegistry in `src/hunters/` (plugin layer). FontCache interacts via ports. |
| **II. Cross-Platform** | ✅ PASS | `pathlib.Path` everywhere. System font discovery uses `fontTools` (cross-platform). Cache path configurable. |
| **III. Async-First I/O** | ✅ PASS | `httpx.AsyncClient` for network hunters. Startup ping via `asyncio.TaskGroup`. Cache file reads via `asyncio.to_thread()` for large scans. |
| **IV. Structured Errors** | ✅ PASS | `FontMatchError` raised on full chain exhaustion with audit trail. `HunterError` for individual source failures. |
| **V. Plugin Registry** | ✅ PASS | `HunterRegistry` supports runtime registration, priority-ordered iteration, circuit breaker skip. Open/Closed Principle enforced. |
| **VI. Data Safety** | ✅ PASS | Atomic cache writes (temp file + rename). `font_library.toml` updates atomic. |
| **VII. Subprocess Lifecycle** | ✅ N/A | No new subprocess calls in this feature. MKV extraction hunter delegates to existing `mkvmerge`/`mkvextract` adapters. |
| **VIII. Encoding Guarantees** | ✅ PASS | SubtitleRepair handles ASS parsing. Font name normalization encoding-preserving. |
| **IX. Observability** | ✅ PASS | CircuitBreaker state transitions logged. Cache hits/misses logged. Hunter results logged. `cache_version` validation logged. |
| **X-bis. Pipeline Report** | ✅ N/A | Report generation consumes FontAsset data — no changes needed here. |
| **X. Test-First** | ✅ PASS | Unit tests for CircuitBreaker, FontCache, HunterRegistry, SubtitleRepair. Contract tests for HunterProtocol. |
| **XI. Dependency Isolation** | ✅ PASS | Only approved deps: pydantic, httpx, fontTools, structlog. |
| **XII. Simplicity/YAGNI** | ✅ PASS | HunterRegistry justified (multiple implementations from day one). CircuitBreaker is minimal state machine. No premature ORM. |
| **XIII. Distribution** | ✅ PASS | Cache on `D:` drive per constitution. Self-describing cache (no config dependency for discovery). |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/003-font-system/
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
├── models/              # [EXISTING + MODIFIED]
│   ├── font.py          # [MODIFY] Add FontPayload model
│   └── __init__.py      # [MODIFY] Export FontPayload
├── ports/               # [EXISTING + NEW]
│   ├── font_hunter.py   # [NEW] HunterProtocol + FontPayload port
│   └── __init__.py      # [MODIFY] Export HunterProtocol
├── core/                # [NEW]
│   ├── __init__.py
│   ├── circuit_breaker.py   # [NEW] CircuitBreaker state machine
│   ├── font_cache.py        # [NEW] FontCache manager
│   ├── font_resolver.py     # [NEW] 6-layer resolution orchestrator
│   └── subtitle_repair.py   # [NEW] ASS font extraction + repair
├── hunters/             # [NEW]
│   ├── __init__.py
│   └── registry.py      # [NEW] HunterRegistry
├── config.py            # [MODIFY] Add circuit_breaker_cooldown_s, font_cache_path
└── errors.py            # [MODIFY] Add FontMatchError, HunterError, EncodingRepairError

tests/
├── unit/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_circuit_breaker.py
│   │   ├── test_font_cache.py
│   │   ├── test_font_resolver.py
│   │   └── test_subtitle_repair.py
│   └── hunters/
│       ├── __init__.py
│       └── test_registry.py
├── contract/
│   ├── __init__.py
│   └── test_hunter_protocol.py
└── fixtures/
    └── ass_samples/     # [NEW] Sample ASS files for subtitle repair tests
```

**Structure Decision**: Follows constitution file organization (§I). Core logic in `src/core/` (stateless, async). Ports in `src/ports/`. Hunters in `src/hunters/`. Models in `src/models/`. Tests mirror source structure.

## Key Design Decisions

| Decision | Rationale | Research Ref |
|----------|-----------|--------------|
| CircuitBreaker in `src/core/`, not in hunters | Constitution §I — business logic belongs in core. Hunters are plugin layer. | R-001 |
| In-memory state machine (no persistence) | YAGNI (§XII) — sessions are short. Circuit state has no value across restarts. | R-002 |
| Startup ping as `asyncio.TaskGroup` fire-and-forget | Constitution §III — async-first. TaskGroup ensures structured concurrency + 2s timeout. | R-003 |
| FontPayload as Pydantic model with `bytes` field | Carries raw font data for cache write-back. Pydantic validates metadata. | R-004 |
| `font_library.toml` with `cache_version` | Constitution §IX — cache versioning mandate. TOML for human readability. | R-005 |
| HunterProtocol as `typing.Protocol` + `@runtime_checkable` | Constitution §V — plugin registry. Static + runtime type safety. | R-006 |
| `match` statement for CircuitBreaker state transitions | Python 3.11+ (§XI). Cleaner than if/elif chain. Exhaustive pattern matching. | R-007 |

## Complexity Tracking

> No violations — table empty.
