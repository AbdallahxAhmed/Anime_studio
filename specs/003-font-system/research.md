# Research: Font System

**Feature**: 003-font-system | **Date**: 2026-05-26

## R-001: CircuitBreaker Placement — Core vs. Hunter Layer

**Decision**: CircuitBreaker state machine lives in `src/core/circuit_breaker.py`.

**Rationale**: Constitution §I mandates business logic in `src/core/`. The circuit breaker governs resolution strategy — it decides whether to attempt a hunter, not how the hunter operates. This separation lets the CircuitBreaker be unit-tested without any network I/O.

**Alternatives considered**:
- **In each hunter**: Rejected — duplicates state machine logic, violates DRY, makes testing harder.
- **In HunterRegistry**: Considered — registry is in `src/hunters/` (plugin layer). CB logic would leak infrastructure concern into plugin container. Registry should only iterate; CB should only track failures.
- **Shared mixin/base class**: Rejected — Protocol-based architecture means no base class. Mixin complicates the type hierarchy.

## R-002: In-Memory vs. Persistent Circuit Breaker

**Decision**: In-memory only. Circuit state resets on each application session.

**Rationale**: YAGNI (§XII). Anime Studio sessions are typically short (process one series → exit). Persisting circuit state adds complexity (file I/O, stale state management) with no user benefit. The startup ping already pre-checks availability each session.

**Alternatives considered**:
- **SQLite persistence**: Rejected — §XII forbids ORM. Circuit state is transient by nature.
- **JSON/TOML cache**: Rejected — cache could become stale (source recovers between sessions). Startup ping makes persistence redundant.

## R-003: Startup Ping Strategy

**Decision**: Fire concurrent HEAD requests via `asyncio.TaskGroup` with a 2-second per-task timeout. Each ping result maps to an initial circuit state.

**Rationale**: Constitution §III mandates async-first. `TaskGroup` (Python 3.11+) provides structured concurrency with automatic cancellation on failure. HEAD request is lightweight (~100 bytes). 2s timeout ensures startup is never blocked.

**Implementation detail**: Each network hunter exposes a `ping_url: str | None` property. If `None`, no ping sent (local hunters). The ping is a simple `httpx.AsyncClient.head(url, timeout=2.0)`. Success → CLOSED. Any failure → OPEN.

**Alternatives considered**:
- **Sequential pings**: Rejected — N hunters × 2s timeout = unacceptable startup time.
- **No startup ping**: Rejected — user explicitly requested fast-fail to prevent startup delays.
- **TCP socket probe**: Considered — lighter than HTTP HEAD but doesn't verify application-layer health. HTTP HEAD preferred for accuracy.

## R-004: FontPayload Design

**Decision**: `FontPayload` is a frozen Pydantic `BaseModel` with `font_data: bytes`, `font_name: str`, `file_extension: str`, `source: str`, `metadata: dict[str, str]`.

**Rationale**: Pydantic enforces validation. `bytes` field holds raw font file content. Metadata captures source-specific info (download URL, license, etc.) for audit trail. Extension needed for correct filename in cache.

**Alternatives considered**:
- **Return file path directly**: Rejected — hunter might download to temp dir. FontPayload decouples download from cache write.
- **Streaming response**: Rejected — fonts are small (typically <1MB). Full in-memory load is acceptable and simpler.

## R-005: Font Library Index Format

**Decision**: TOML file (`font_library.toml`) with structure:

```toml
cache_version = "3.0"

[fonts."Roboto-Regular"]
file = "Roboto-Regular.ttf"
source = "google_fonts"
layer_found = 5
added = "2026-05-26T10:30:00"
nameids = {1 = "Roboto", 2 = "Regular", 4 = "Roboto Regular"}

[fonts."NotoSansCJK-Bold"]
file = "NotoSansCJK-Bold.otf"
source = "system"
layer_found = 4
added = "2026-05-26T10:31:00"
nameids = {1 = "Noto Sans CJK JP", 2 = "Bold"}
```

**Rationale**: Constitution §IX mandates `cache_version`. TOML is human-readable (§XII), stdlib-supported in 3.11+ (`tomllib`). Font name as key enables O(1) lookup.

**Alternatives considered**:
- **JSON**: Rejected — less readable, no comments support.
- **SQLite**: Rejected — §XII forbids ORM. Overkill for simple key-value index.
- **Scanning directory on every lookup**: Rejected — too slow for 500+ fonts.

## R-006: HunterProtocol Type Safety

**Decision**: `typing.Protocol` with `@runtime_checkable`. All method signatures use domain model types (no `Any`, no `dict`).

**Rationale**: Constitution §V mandates strictly typed protocol. `@runtime_checkable` enables `isinstance()` check at registration time (fail-fast). Static analysis via `mypy --strict` catches interface violations at dev time.

**Key signature decisions**:
- `search()` returns `list[HunterResult]` (not generator) — results are small, full materialization acceptable.
- `download()` returns `FontPayload` (not `bytes`) — structured result with metadata.
- `supports()` is synchronous — it's a lightweight capability check, no I/O.

## R-007: match Statement for CircuitBreaker

**Decision**: Use Python `match` statement for state transition logic.

**Rationale**: Constitution §XI permits Python 3.11+ features. `match` provides exhaustive pattern matching over `CircuitBreakerState` enum, making impossible states unrepresentable. Cleaner than if/elif chains.

```python
match self._state:
    case CircuitBreakerState.CLOSED:
        ...
    case CircuitBreakerState.OPEN:
        ...
    case CircuitBreakerState.HALF_OPEN:
        ...
```
