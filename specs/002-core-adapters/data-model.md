# Data Model: Core Adapters Layer

**Feature**: 002-core-adapters | **Date**: 2026-05-26

## Entities

### 1. BinaryClassification (Enum)

**Module**: `src/adapters/dependency_checker.py`
**Type**: `StrEnum`

| Value | Meaning |
|-------|---------|
| `CRITICAL` | App refuses to start without this binary |
| `OPTIONAL` | Reduced features + WARNING when missing |

### 2. BinarySpec (Value Object)

**Module**: `src/adapters/dependency_checker.py`
**Type**: `Pydantic BaseModel (frozen=True)`

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| `name` | `str` | `min_length=1` | Binary name (e.g., `ffmpeg`) |
| `classification` | `BinaryClassification` | — | CRITICAL or OPTIONAL |
| `install_hint` | `str` | — | Human-readable install instruction |

### 3. ResolvedTool (Value Object)

**Module**: `src/adapters/dependency_checker.py`
**Type**: `Pydantic BaseModel (frozen=True)`

| Field | Type | Constraint | Description |
|-------|------|------------|-------------|
| `name` | `str` | `min_length=1` | Binary name |
| `path` | `SerializablePath` | — | Resolved absolute path to binary |
| `classification` | `BinaryClassification` | — | CRITICAL or OPTIONAL |

### 4. ToolRegistry (Container)

**Module**: `src/adapters/dependency_checker.py`
**Type**: Plain class (not Pydantic — has query methods)

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `(name: str) -> Path` | Get resolved path; raise `ToolNotFoundError` if not registered |
| `is_available` | `(name: str) -> bool` | Check if tool was discovered |
| `all_tools` | `() -> dict[str, ResolvedTool]` | All registered tools |

### 5. AppConfig (Settings)

**Module**: `src/config.py`
**Type**: `Pydantic BaseSettings`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `proxy` | `str \| None` | `None` | Network proxy URL |
| `max_concurrent_disk_io` | `int` | `3` | Semaphore limit for bulk mux/extract |
| `default_timeout_s` | `float` | `120.0` | Default subprocess timeout |
| `mux_timeout_s` | `float` | `300.0` | Mux operation timeout |
| `trash_max_age_days` | `int` | `30` | Trash cleanup threshold |

**Config source**: `%APPDATA%\AnimeStudio\config.toml` (Windows) or `~/.config/anime_studio/config.toml` (Linux/macOS)

### 6. Error Taxonomy (Partial)

**Module**: `src/errors.py`

```
AnimeStudioError (base)
├── ToolNotFoundError      # CRITICAL binary missing
├── ToolExecutionError     # Binary ran but non-zero exit
└── ConfigurationError     # Invalid config (e.g., malformed proxy)
```

## Existing Models (from 001-domain-models)

These are consumed by adapters, not modified:

- `ToolResult` — subprocess execution result envelope
- `SerializablePath` — cross-platform path type alias

## Relationships

```
AppConfig ──reads──> DependencyChecker ──produces──> ToolRegistry
                                                         │
SubprocessPort ──uses──> ToolResult                      │
     │                                                   │
     └──────────uses paths from──────────────────────────┘

HttpClientPort ──reads proxy from──> AppConfig
```

## Port Protocols

### SubprocessPort

```
@runtime_checkable
class SubprocessPort(Protocol):
    async def execute(
        self,
        command: list[str],
        *,
        tool_name: str,
        timeout_s: float = 120.0,
        cwd: Path | None = None,
    ) -> ToolResult: ...
```

### HttpClientPort

```
@runtime_checkable
class HttpClientPort(Protocol):
    def create_client(
        self,
        *,
        timeout_s: float = 30.0,
    ) -> httpx.AsyncClient: ...
```

## State Transitions

No state machines in this layer. `DependencyChecker` is a one-shot startup operation. `SubprocessPort` and `HttpClientPort` are stateless request/response.

## Validation Rules

| Rule | Location | Behavior |
|------|----------|----------|
| Binary path must be existing file | `DependencyChecker` | Skip path, try next step |
| Binary path must be executable | `DependencyChecker` | Skip path, try next step |
| All CRITICAL missing → aggregate error | `DependencyChecker` | Single `ToolNotFoundError` |
| Proxy URL must be valid | `HttpClientAdapter` | `ConfigurationError` at construction |
| Timeout must be positive | `SubprocessPort.execute()` | `ValueError` |
