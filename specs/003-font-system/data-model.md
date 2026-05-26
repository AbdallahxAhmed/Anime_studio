# Data Model: Font System

**Feature**: 003-font-system | **Date**: 2026-05-26

## New Models

### FontPayload

**Module**: `src/models/font.py`
**Purpose**: Carries raw font bytes + metadata from hunter download to cache write-back.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `font_name` | `str` | `min_length=1` | Canonical font name (from nameID 4 or 1) |
| `font_data` | `bytes` | `min_length=1` | Raw font file content |
| `file_extension` | `str` | `min_length=1` | Extension including dot (`.ttf`, `.otf`, `.woff2`) |
| `source` | `str` | `min_length=1` | Hunter/source identifier |
| `nameids` | `dict[int, str]` | — | OpenType name table entries |
| `metadata` | `dict[str, str]` | `default_factory=dict` | Source-specific metadata (URL, license, etc.) |

Config: `frozen=True`

### CircuitBreakerState

**Module**: `src/core/circuit_breaker.py`
**Purpose**: Enum representing circuit breaker states.

| Value | Description |
|-------|-------------|
| `CLOSED` | Normal operation. Requests flow through. |
| `OPEN` | Tripped. All requests fast-fail. |
| `HALF_OPEN` | Probing. Single request allowed. |

### CircuitBreaker

**Module**: `src/core/circuit_breaker.py`
**Purpose**: In-memory state machine tracking per-hunter failure counts.

| Field | Type | Description |
|-------|------|-------------|
| `_state` | `CircuitBreakerState` | Current state (default: CLOSED) |
| `_failure_count` | `int` | Consecutive failure count |
| `_threshold` | `int` | Failures before OPEN (from hunter config) |
| `_cooldown_s` | `float` | Seconds before OPEN → HALF_OPEN |
| `_last_failure_time` | `float | None` | Monotonic timestamp of last failure |
| `_hunter_name` | `str` | For logging context |

Methods:
- `record_success() -> None` — Reset to CLOSED, clear failure count.
- `record_failure() -> None` — Increment failure count, transition if threshold met.
- `can_execute() -> bool` — Check if request should proceed based on state + cooldown.
- `state -> CircuitBreakerState` — Current state property.

**Not a Pydantic model** — mutable internal state. Plain class with `__slots__`.

### FontCacheEntry

**Module**: `src/core/font_cache.py` (internal, not exported)
**Purpose**: Represents one entry in `font_library.toml`.

| Field | Type | Description |
|-------|------|-------------|
| `file` | `str` | Filename in `font_cache/` directory |
| `source` | `str` | How font was acquired |
| `layer_found` | `int` | Which layer resolved it (1-6) |
| `added` | `str` | ISO 8601 timestamp |
| `nameids` | `dict[int, str]` | OpenType name table entries |

Config: `frozen=True` (Pydantic model, internal to FontCache)

## Modified Models

### FontAsset (existing)

No structural changes. `layer_found` field range already covers 0-6.

### AppConfig (existing `src/config.py`)

Add fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `circuit_breaker_cooldown_s` | `float` | `60.0` | Seconds before OPEN → HALF_OPEN |
| `font_cache_path` | `Path | None` | `None` | Override for font cache directory. If `None`, uses `D:\Entertainment\.anime_studio\font_cache\` |
| `startup_ping_timeout_s` | `float` | `2.0` | Max time for startup ping |

### errors.py (existing)

Add exceptions:

| Exception | Parent | Description |
|-----------|--------|-------------|
| `FontMatchError` | `AnimeStudioError` | All hunters exhausted, no font found |
| `HunterError` | `AnimeStudioError` | Individual hunter failure |
| `EncodingRepairError` | `AnimeStudioError` | ASS file structure unrecoverable |

## Entity Relationships

```
FontQuery ──→ HunterRegistry ──→ HunterProtocol (N implementations)
                    │                     │
                    │                     ▼
                    │               FontPayload
                    │                     │
                    ▼                     ▼
              CircuitBreaker ←──── FontCache
                                       │
                                       ▼
                                  FontAsset
```

- `FontQuery` is input to resolution.
- `HunterRegistry` iterates `HunterProtocol` implementations.
- Each hunter returns `FontPayload` on success.
- `FontCache` writes `FontPayload` → disk, returns `FontAsset`.
- `CircuitBreaker` is checked before each hunter invocation.
