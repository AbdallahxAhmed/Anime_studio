# Quickstart: Core Adapters Layer

**Feature**: 002-core-adapters | **Date**: 2026-05-26

## Prerequisites

- Python 3.11+
- `pydantic` and `httpx` installed (via `uv`)
- `ffmpeg`, `mkvmerge`, `mkvextract` installed (via Scoop or system PATH)

## Usage Examples

### 1. Tool Discovery at Startup

```python
from src.adapters.dependency_checker import DependencyChecker

checker = DependencyChecker()
registry = checker.discover_all()
# registry.get("ffmpeg") -> Path("C:/Users/user/scoop/shims/ffmpeg.exe")
# registry.is_available("alass") -> False (OPTIONAL, logged WARNING)
```

### 2. Running a Subprocess

```python
from src.adapters.subprocess import SubprocessAdapter
from src.models import ToolResult

adapter = SubprocessAdapter()
result: ToolResult = await adapter.execute(
    ["ffmpeg", "-version"],
    tool_name="ffmpeg",
    timeout_s=30.0,
)
assert result.success
assert result.exit_code == 0
print(result.stdout)
```

### 3. Creating an HTTP Client

```python
from src.adapters.http_client import HttpClientAdapter
from src.config import AppConfig

config = AppConfig()  # reads from config.toml
adapter = HttpClientAdapter(proxy=config.proxy)

async with adapter.create_client(timeout_s=15.0) as client:
    response = await client.get("https://api.example.com/fonts")
```

### 4. Port-Based Testing (Mocking)

```python
from unittest.mock import AsyncMock
from src.ports.subprocess import SubprocessPort
from src.models import ToolResult

mock_port = AsyncMock(spec=SubprocessPort)
mock_port.execute.return_value = ToolResult(
    tool_name="ffmpeg",
    success=True,
    exit_code=0,
    stdout="ffmpeg version 7.0",
    stderr="",
    duration_ms=50.0,
)

# Core service uses the port — no real subprocess
result = await mock_port.execute(["ffmpeg", "-version"], tool_name="ffmpeg")
assert result.success
```

## Test Commands

```bash
# Unit tests (mocked, no real binaries needed)
pytest tests/unit/adapters/ -v

# Integration tests (requires real binaries)
pytest tests/integration/adapters/ -v -m integration

# Import validation (strict layering)
python -c "import ast, sys; [check_imports(f) for f in src_adapters_files]"
```

## Verification Checklist

- [ ] `DependencyChecker` finds Scoop-installed ffmpeg
- [ ] Missing mkvmerge raises `ToolNotFoundError` with install hint
- [ ] Missing alass logs WARNING, app continues
- [ ] Subprocess timeout kills process and returns `ToolResult(success=False)`
- [ ] HTTP client uses proxy from config.toml
- [ ] No file in `src/adapters/` imports from `src/core/`
