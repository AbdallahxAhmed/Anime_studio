# Research: Core Adapters Layer

**Feature**: 002-core-adapters | **Date**: 2026-05-26

## R-001: Windows-First Tool Discovery Order

**Decision**: Implement 5-step discovery per Constitution §XIII.

**Rationale**: Scoop is dominant package manager for Windows media tools. `C:\Program Files\mpv\` catches mpv-config bundled ffmpeg. `shutil.which()` is universal fallback.

**Implementation notes**:
- Steps 1-4 use `pathlib.Path.home()` and `pathlib.Path.glob()` for cross-platform safety
- Step 2 and 4 use `**` glob patterns — must limit depth to avoid excessive scanning
- On non-Windows (`sys.platform != "win32"`), steps 1-4 are skipped entirely
- Discovery must verify the resolved path is an existing executable file (`Path.is_file()` + access check)

**Alternatives considered**:
- Registry-based discovery (Windows Registry): Too fragile, tool-specific, not portable
- Environment variable per tool: Workable but high user friction
- Config-only paths: Defeats purpose of zero-config startup

## R-002: Binary Classification Strategy

**Decision**: Two tiers — CRITICAL (hard fail) and OPTIONAL (soft warn). ALWAYS AVAILABLE tier not resolved at runtime.

**Rationale**: Constitution §XIII table defines exact classification. ALWAYS AVAILABLE binaries (`ffsubsync`, `fonttools`, `charset-normalizer`) are Python packages managed by `uv`, not discovered as binaries.

**Implementation notes**:
- CRITICAL: `ffmpeg`, `mkvmerge`, `mkvextract` — `ToolNotFoundError` with install instructions
- OPTIONAL: `alass`, `ots-sanitize` — WARNING log, feature disabled gracefully
- `yt-dlp` is OPTIONAL per constitution but deferred to later feature
- Error for missing CRITICAL tools MUST aggregate all missing tools into single error message

**Alternatives considered**:
- Three tiers at adapter level: Unnecessary — ALWAYS AVAILABLE are Python packages
- Per-adapter discovery: Scatter discovery across adapters instead of centralized checker — harder to test, harder to report aggregated errors

## R-003: Subprocess Port Design

**Decision**: `typing.Protocol` in `src/ports/subprocess.py` with single `execute()` method. Implementation in `src/adapters/subprocess.py`.

**Rationale**: Constitution §IV mandates `ToolResult` return. Constitution §III mandates `asyncio.create_subprocess_exec()`. Single method keeps interface minimal (YAGNI, §XII).

**Implementation notes**:
- `execute(command: list[str], *, timeout_s: float = 120.0, tool_name: str, cwd: Path | None = None) -> ToolResult`
- Use `asyncio.wait_for()` for timeout enforcement
- Catch `FileNotFoundError`, `asyncio.TimeoutError`, `OSError` → convert to `ToolResult(success=False)`
- Decode stdout/stderr with `errors="replace"` for non-UTF-8 safety
- Measure duration with `time.perf_counter()` → milliseconds
- For disk-intensive operations (mux/extract), caller provides `semaphore` param or adapter acquires from config

**Alternatives considered**:
- Return `ToolResult | ToolExecutionError`: Mixing return types adds complexity. Single `ToolResult` with `success=False` is simpler.
- Separate method per tool: Violates Open/Closed. Single `execute()` + command list is generic.

## R-004: HTTPX Port Design

**Decision**: `typing.Protocol` in `src/ports/http_client.py`. Adapter in `src/adapters/http_client.py`.

**Rationale**: Constitution §III mandates `httpx.AsyncClient` with proxy from config. Adapter wraps client creation to enforce proxy, timeout, and retry policies.

**Implementation notes**:
- Protocol method: `create_client() -> httpx.AsyncClient`
- Adapter constructor takes proxy URL (from config) and timeout settings
- Retry via `httpx` transport-level retry or manual retry wrapper
- `httpx.AsyncClient` is used as async context manager — adapter provides factory, caller manages lifecycle
- Malformed proxy URL → `ConfigurationError` at adapter construction

**Alternatives considered**:
- Wrap every HTTP method (get, post, etc.): Over-abstraction. Returning configured `AsyncClient` is simpler (§XII)
- Global singleton client: Against DI principle. Factory pattern allows per-use configuration.

## R-005: Error Taxonomy Scope

**Decision**: Define `ToolNotFoundError`, `ToolExecutionError`, `ConfigurationError` in `src/errors.py` for this feature. Full taxonomy exists in constitution §IV.

**Rationale**: Only errors needed by adapters layer. Remaining errors (`EncodingRepairError`, `FontMatchError`, etc.) are core/hunter concerns for later features.

**Alternatives considered**:
- Define all errors now: YAGNI. Only define what this feature needs.
- Inline errors in adapter files: Violates centralization mandate.

## R-006: Config Scope

**Decision**: Define minimal `AppConfig` in `src/config.py` with Pydantic `BaseSettings`. Fields: `proxy`, `max_concurrent_disk_io`, `default_timeout_s`, `mux_timeout_s`.

**Rationale**: Constitution mandates `config.toml` with `BaseSettings`. Only define fields consumed by this feature.

**Alternatives considered**:
- Full config schema now: YAGNI. Incremental config growth across features.
- Separate config per adapter: Over-fragmented. Single config is simpler (§XII).
