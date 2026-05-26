# Port Contracts: Core Adapters Layer

**Feature**: 002-core-adapters | **Date**: 2026-05-26

These contracts define the port interfaces that adapters implement and core services consume.

## SubprocessPort Contract

**File**: `src/ports/subprocess.py`

```python
@runtime_checkable
class SubprocessPort(Protocol):
    """Async contract for executing external tool processes."""

    async def execute(
        self,
        command: list[str],
        *,
        tool_name: str,
        timeout_s: float = 120.0,
        cwd: Path | None = None,
    ) -> ToolResult:
        """
        Execute a subprocess and return structured result.

        Args:
            command: Full command as list of strings (e.g., ["ffmpeg", "-version"])
            tool_name: Name for ToolResult.tool_name field
            timeout_s: Maximum execution time in seconds. Process is killed on timeout.
            cwd: Working directory for the subprocess. None = inherit.

        Returns:
            ToolResult with captured stdout, stderr, exit code, duration, and suggestion.

        Guarantees:
            - NEVER raises raw exceptions to the caller
            - ALWAYS returns a ToolResult (success=True or success=False)
            - ALWAYS kills timed-out processes
            - ALWAYS decodes output as UTF-8 with errors="replace"
        """
        ...
```

### Behavioral Contract

| Scenario | `success` | `exit_code` | `suggestion` |
|----------|-----------|-------------|--------------|
| Normal completion, exit 0 | `True` | `0` | `None` |
| Normal completion, exit ≠ 0 | `False` | actual code | Tool-specific hint |
| Timeout | `False` | `-1` | "Process timed out after {timeout_s}s" |
| Binary not found | `False` | `-1` | "'{tool_name}' not found on system" |
| OS error | `False` | `-1` | Error description |

---

## HttpClientPort Contract

**File**: `src/ports/http_client.py`

```python
@runtime_checkable
class HttpClientPort(Protocol):
    """Contract for creating configured httpx.AsyncClient instances."""

    def create_client(
        self,
        *,
        timeout_s: float = 30.0,
    ) -> httpx.AsyncClient:
        """
        Create an httpx.AsyncClient with proxy and timeout pre-configured.

        Args:
            timeout_s: Request timeout in seconds.

        Returns:
            Configured httpx.AsyncClient. Caller manages lifecycle (async with).

        Raises:
            ConfigurationError: If proxy URL is malformed (at construction, not here).
        """
        ...
```

### Behavioral Contract

| Scenario | Behavior |
|----------|----------|
| Proxy set in config | Client uses proxy for all requests |
| No proxy in config | Client uses direct connection |
| Malformed proxy URL | `ConfigurationError` at adapter construction |
| Timeout exceeded | `httpx.TimeoutException` (caller handles) |
| Transient 5xx error | Retry up to configured max (adapter-level) |

---

## DependencyChecker Contract

**File**: `src/adapters/dependency_checker.py` (not a port — this is the concrete implementation)

```python
class DependencyChecker:
    """Discovers and validates external tool binaries at startup."""

    def discover_all(self) -> ToolRegistry:
        """
        Run 5-step discovery for all known binaries.

        Returns:
            ToolRegistry containing all discovered tools.

        Raises:
            ToolNotFoundError: If ANY CRITICAL binary is missing.
                Error message lists ALL missing CRITICAL binaries.
        """
        ...

    def discover_one(self, spec: BinarySpec) -> ResolvedTool | None:
        """
        Discover a single binary using the 5-step search order.

        Returns:
            ResolvedTool if found, None if not found.
        """
        ...
```

### Discovery Order Contract

| Step | Path Pattern | Platform |
|------|-------------|----------|
| 1 | `~/scoop/shims/<tool>.exe` | Windows only |
| 2 | `~/scoop/apps/<tool>/current/**/<tool>.exe` | Windows only |
| 3 | `C:\Program Files\mpv\<tool>.exe` | Windows only |
| 4 | `C:\Program Files\<Tool>\**\<tool>.exe` | Windows only |
| 5 | `shutil.which(<tool>)` | All platforms |
