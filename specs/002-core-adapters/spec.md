# Feature Specification: Core Adapters Layer

**Feature Branch**: `002-core-adapters`

**Created**: 2026-05-26

**Status**: Draft

**Input**: User description: "Phase 1 — Core Adapters. Implement tool discovery (DependencyChecker) with 5-step Windows-first binary discovery, binary classification (CRITICAL/OPTIONAL), async subprocess port returning ToolResult with timeouts, HTTPX port reading network proxy config, strict layering where src/adapters/ only imports from src/models/ and src/ports/."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tool Discovery & Binary Classification (Priority: P1)

A developer setting up the Anime Studio runtime needs an automated system that discovers external tool binaries (ffmpeg, mkvmerge, mkvextract, alass, ots-sanitize) at startup using a Windows-first 5-step search order. CRITICAL binaries that are missing must prevent the application from operating. OPTIONAL binaries that are missing must degrade gracefully with a logged warning.

**Why this priority**: Without tool discovery, no adapter can function. Every subprocess adapter depends on knowing where binaries live. This is the foundational gate for the entire adapters layer.

**Independent Test**: Can be fully tested by mocking filesystem paths and `shutil.which()` to simulate present/absent binaries across all 5 discovery steps, verifying CRITICAL binaries raise `ToolNotFoundError` and OPTIONAL binaries log warnings.

**Acceptance Scenarios**:

1. **Given** ffmpeg is installed via Scoop, **When** `DependencyChecker` runs discovery, **Then** it finds ffmpeg at `~/scoop/shims/ffmpeg.exe` (step 1) and registers the resolved path.
2. **Given** mkvmerge is not installed anywhere, **When** `DependencyChecker` runs discovery, **Then** it raises `ToolNotFoundError` with a message containing installation instructions for MKVToolNix.
3. **Given** alass is not installed, **When** `DependencyChecker` runs discovery, **Then** it logs a WARNING "alass not found — subtitle sync will use ffsubsync only" and marks the tool as unavailable.
4. **Given** the application runs on Linux, **When** `DependencyChecker` runs discovery, **Then** only step 5 (`shutil.which()`) is used — Windows-specific paths are skipped.
5. **Given** ffmpeg exists at both Scoop shims and `C:\Program Files\mpv\`, **When** discovery runs, **Then** the Scoop shims path wins (first match in the 5-step order).

---

### User Story 2 - Async Subprocess Execution Port (Priority: P1)

A developer building tool-specific adapters (ffmpeg, mkvmerge, alass) needs a clean async interface for executing external processes that guarantees: returning a `ToolResult` model, enforcing configurable timeouts, capturing stdout/stderr, preventing raw tracebacks from leaking to users, and measuring execution duration.

**Why this priority**: Constitution Principles IV and VII mandate structured subprocess execution. Every tool adapter depends on this port. Without it, adapters cannot be implemented.

**Independent Test**: Can be fully tested by defining a mock implementation of the subprocess port that returns canned `ToolResult` values, and by writing an integration test that runs a real process (e.g., `echo hello`) through the port.

**Acceptance Scenarios**:

1. **Given** a valid command (e.g., `ffmpeg -version`), **When** executed through the subprocess port, **Then** a `ToolResult` is returned with `success=True`, `exit_code=0`, populated `stdout`, empty `stderr`, and `duration_ms > 0`.
2. **Given** a command that exceeds the configured timeout (default 120s), **When** executed through the subprocess port, **Then** the process is killed, and a `ToolResult` is returned with `success=False` and `suggestion` containing "timed out".
3. **Given** a command that fails with exit code 1, **When** executed through the subprocess port, **Then** a `ToolResult` is returned with `success=False`, the correct `exit_code`, and captured `stderr`.
4. **Given** a command that does not exist on the system, **When** executed through the subprocess port, **Then** a `ToolResult` is returned with `success=False` and `suggestion` containing "not found" — no raw `FileNotFoundError` traceback.

---

### User Story 3 - HTTP Client Port with Proxy Support (Priority: P2)

A developer building network-dependent adapters (font hunters, API clients) needs a base HTTP adapter that creates `httpx.AsyncClient` instances pre-configured with: proxy settings from `config.toml`, explicit timeouts, connection pooling, and retry policies. The port must enforce Constitution Principle III (network proxying mandate).

**Why this priority**: Network access is needed by hunters and update checkers, but the core pipeline (tool discovery + subprocess) can function without it. This is important but not blocking for the initial MVP.

**Independent Test**: Can be fully tested by verifying the adapter reads proxy config, passes it to `httpx.AsyncClient`, and applies timeout/retry policies — all mockable without real network calls.

**Acceptance Scenarios**:

1. **Given** `config.toml` contains `proxy = "socks5://127.0.0.1:1080"`, **When** the HTTP adapter creates a client, **Then** the `httpx.AsyncClient` is instantiated with `proxy="socks5://127.0.0.1:1080"`.
2. **Given** `config.toml` has no `proxy` field or it is empty, **When** the HTTP adapter creates a client, **Then** no proxy is configured on the `httpx.AsyncClient`.
3. **Given** the HTTP adapter is used to make a request, **When** the request times out, **Then** the adapter returns a structured error (not a raw `httpx.TimeoutException` traceback).
4. **Given** a transient server error (HTTP 503), **When** the adapter makes a request with retry policy, **Then** it retries up to the configured maximum before reporting failure.

---

### User Story 4 - Port Interface Definitions (Priority: P1)

A developer needs clean, minimal `typing.Protocol` definitions in `src/ports/` that define the contracts for subprocess execution and HTTP client creation. These protocols decouple adapters from core logic and enable testing with mock implementations.

**Why this priority**: Ports are the architectural linchpin — without them, the hexagonal boundary between core and adapters does not exist. They must be defined before any adapter implementation.

**Independent Test**: Can be fully tested by verifying protocol definitions are syntactically valid, that a mock class satisfying the protocol passes `isinstance` checks (via `runtime_checkable`), and that the protocols import only from `src/models/`.

**Acceptance Scenarios**:

1. **Given** the `SubprocessPort` protocol, **When** a class implements its `execute()` method returning `ToolResult`, **Then** it satisfies the protocol contract at runtime.
2. **Given** the `HttpClientPort` protocol, **When** a class implements its client factory method, **Then** it satisfies the protocol contract at runtime.
3. **Given** any port definition file, **When** its imports are inspected, **Then** it imports only from `src/models/`, the standard library, or `typing`.

---

### Edge Cases

- What happens when a CRITICAL binary path exists but the file is not executable? Discovery should verify executability, not just path existence.
- What happens when `shutil.which()` returns a path that is a symlink to a non-existent target? The checker should validate the resolved path exists.
- What happens when subprocess stdout/stderr contains non-UTF-8 bytes? The port must decode with `errors="replace"` to avoid `UnicodeDecodeError`.
- What happens when the proxy URL in `config.toml` is malformed? The HTTP adapter should raise `ConfigurationError` at construction time, not at first request.
- What happens when multiple CRITICAL binaries are missing? `DependencyChecker` should report ALL missing binaries in a single error, not fail on the first.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement a `DependencyChecker` that discovers external binaries using a 5-step Windows-first search order: (1) `~/scoop/shims/<tool>.exe`, (2) `~/scoop/apps/<tool>/current/**/<tool>.exe`, (3) `C:\Program Files\mpv\<tool>.exe`, (4) `C:\Program Files\<Tool>\**\<tool>.exe`, (5) `shutil.which(<tool>)`
- **FR-002**: On non-Windows platforms, `DependencyChecker` MUST skip steps 1-4 and use only step 5
- **FR-003**: CRITICAL binaries (`ffmpeg`, `mkvmerge`, `mkvextract`) MUST raise `ToolNotFoundError` with installation instructions when not found
- **FR-004**: OPTIONAL binaries (`alass`, `ots-sanitize`) MUST log a WARNING and disable dependent features when not found
- **FR-005**: `DependencyChecker` MUST report ALL missing CRITICAL binaries in a single error, not fail on the first
- **FR-006**: System MUST define a `SubprocessPort` protocol with an `execute()` method that accepts command arguments and returns `ToolResult`
- **FR-007**: The subprocess port implementation MUST use `asyncio.create_subprocess_exec()` — blocking `subprocess.run()` is FORBIDDEN
- **FR-008**: The subprocess port MUST enforce configurable timeouts (default: 120s for sync, 300s for mux) and kill timed-out processes
- **FR-009**: The subprocess port MUST capture stdout and stderr, decoding with `errors="replace"` for non-UTF-8 safety
- **FR-010**: The subprocess port MUST measure execution duration in milliseconds and include it in `ToolResult.duration_ms`
- **FR-011**: The subprocess port MUST prevent raw tracebacks — all exceptions MUST be caught and converted to `ToolResult` with `success=False`
- **FR-012**: System MUST define an `HttpClientPort` protocol for creating configured `httpx.AsyncClient` instances
- **FR-013**: The HTTP adapter MUST read the `proxy` field from `config.toml` and pass it to `httpx.AsyncClient`
- **FR-014**: The HTTP adapter MUST apply explicit timeouts and connection pooling to all clients
- **FR-015**: The HTTP adapter MUST implement retry logic for transient errors (HTTP 5xx, connection errors)
- **FR-016**: The HTTP adapter MUST raise `ConfigurationError` for malformed proxy URLs at construction time
- **FR-017**: All files in `src/adapters/` MUST only import from `src/models/`, `src/ports/`, and the standard library — importing from `src/core/`, `src/hunters/`, or `src/tui/` is FORBIDDEN
- **FR-018**: All files in `src/ports/` MUST only import from `src/models/` and the standard library — importing from any other `src/` package is FORBIDDEN
- **FR-019**: `DependencyChecker` MUST verify that discovered binary paths are executable files, not just that the path exists
- **FR-020**: The subprocess port implementation MUST acquire the shared `disk_io_semaphore` (from config) for bulk mux/extract operations before launching subprocess

### Key Entities

- **DependencyChecker**: Service that discovers and validates external tool binaries at startup, classifying them as CRITICAL or OPTIONAL
- **SubprocessPort**: Protocol defining the async contract for executing external processes and returning `ToolResult`
- **HttpClientPort**: Protocol defining the contract for creating proxy-aware, timeout-configured HTTP clients
- **ToolRegistry**: Container holding resolved binary paths after discovery, queryable by tool name

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 3 CRITICAL binaries are discovered and registered when installed, within 500ms total discovery time
- **SC-002**: Missing CRITICAL binaries produce a single actionable error listing all missing tools with installation instructions
- **SC-003**: Missing OPTIONAL binaries produce WARNING-level log messages and the application continues operating with reduced features
- **SC-004**: 100% of subprocess executions return a `ToolResult` — no raw exceptions or tracebacks reach the caller
- **SC-005**: Subprocess timeouts are enforced within 1 second of the configured limit
- **SC-006**: HTTP clients are created with proxy settings matching `config.toml` configuration
- **SC-007**: No file in `src/adapters/` or `src/ports/` imports from `src/core/`, `src/hunters/`, or `src/tui/`
- **SC-008**: All port protocols are `runtime_checkable` and can be verified with `isinstance()` checks in tests

## Assumptions

- Python 3.11+ is the minimum supported version per constitution
- `httpx` is available as a project dependency (approved in constitution §XI)
- `pydantic` is available for `BaseSettings` config validation (approved in constitution §XI)
- The `ToolResult` model already exists in `src/models/tool_result.py` (delivered in 001-domain-models)
- The error taxonomy (`ToolNotFoundError`, `ToolExecutionError`, `ConfigurationError`) will be defined in `src/errors.py` as part of this feature
- `config.toml` schema and `BaseSettings` class will be defined in `src/config.py` as part of this feature (at minimum the fields needed: `proxy`, `max_concurrent_disk_io`, timeout settings)
- Scoop is the primary Windows package manager for tool installation (common in the anime/media community)
- The `disk_io_semaphore` will be application-scoped and injected via config/constructor into adapters
- `yt-dlp` is listed as OPTIONAL in the constitution but is deferred to a later feature — not included in this phase
