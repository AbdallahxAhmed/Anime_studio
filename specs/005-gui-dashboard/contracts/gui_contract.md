# Contract: GUI ↔ PipelineRunner Interface

**Feature**: 005-gui-dashboard | **Date**: 2026-05-26

## Overview

The GUI is a pure consumer of `PipelineRunner`. This contract defines the exact interface surface the GUI touches — nothing more. The GUI MUST NOT import from `src/adapters/`, `src/hunters/`, or `src/core/` directly. All wiring goes through `src/gui/bootstrap.py` (composition root).

## PipelineRunner (consumed as-is from 004-pipeline)

**Module**: `src/core/pipeline_runner.py`

The GUI calls exactly one method:

```python
class PipelineRunner:
    async def run(self, pipeline_config: PipelineConfig) -> PipelineReport: ...
```

### PipelineConfig (consumed from `src/models/pipeline.py`)

```python
class PipelineConfig(BaseModel):
    library_path: Path           # Selected by user via FilePicker
    dry_run: bool = False        # Toggled by checkbox on dashboard
    # ... other fields managed by config.toml, not by GUI
```

The GUI constructs `PipelineConfig` with only `library_path` and `dry_run` — all other fields come from `AppConfig` defaults.

### PipelineReport (consumed from `src/models/report.py`)

```python
class PipelineReport(BaseModel):
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    episode_reports: list[EpisodeReport]
    total_fonts_found: int
    total_fonts_missing: int
    report_path: Path            # Path to _AnimeStudio_Report.md

class EpisodeReport(BaseModel):
    episode_name: str
    status: str                  # "complete", "partial", "failed"
    fonts_found: int
    fonts_missing: int
    errors: list[str]
```

The GUI maps `PipelineReport` → `PipelineRunResult` and `EpisodeReport` → `EpisodeResult` for display purposes. Mapping lives in `bootstrap.py`.

---

## Log Bridge Contract

**Module**: `src/gui/log_bridge.py`

### structlog Processor Interface

The bridge is injected into structlog's processor chain at application startup (in `bootstrap.py`):

```python
class GuiLogBridge:
    """structlog processor that captures INFO+ events to an asyncio.Queue."""

    def __init__(self, queue: asyncio.Queue[dict]) -> None:
        self._queue = queue

    def __call__(
        self,
        logger: Any,
        method_name: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """Intercept and forward; never consume or modify the event."""
        level = event_dict.get("level", "debug")
        if level in ("info", "warning", "error", "critical"):
            self._queue.put_nowait(event_dict)
        return event_dict  # pass through to remaining processors
```

### Queue Protocol

- **Producer**: `GuiLogBridge` processor (runs in pipeline's async context)
- **Consumer**: Activity feed's throttled consumer coroutine (runs in Flet's event loop)
- **Queue type**: `asyncio.Queue[dict[str, Any]]` (unbounded; entries are small dicts)
- **Thread safety**: Both producer and consumer run on the same asyncio event loop — no threading concerns.

---

## Progress Callback Contract

Progress updates flow from PipelineRunner to the GUI via a callback protocol. The callback is injected into PipelineRunner at construction time (via bootstrap).

```python
from typing import Protocol

class ProgressCallback(Protocol):
    async def on_scan_start(self) -> None:
        """Called when library scanning begins. GUI shows spinner."""
        ...

    async def on_scan_complete(self, episode_count: int) -> None:
        """Called when scanning finishes. GUI knows total for progress bar."""
        ...

    async def on_mux_progress(self, completed: int, total: int) -> None:
        """Called when a mux job completes. GUI updates progress bar."""
        ...

    async def on_pipeline_complete(self, report: PipelineReport) -> None:
        """Called when entire pipeline finishes. GUI shows results."""
        ...

    async def on_pipeline_error(self, error: Exception) -> None:
        """Called on unrecoverable error. GUI shows AlertDialog."""
        ...
```

**NOTE**: If PipelineRunner from 004-pipeline does not yet support progress callbacks, the GUI bootstrap will wrap it with a shim that derives progress from structlog events. This is the fallback strategy — no modification to PipelineRunner's contract is required.

---

## Bootstrap Contract

**Module**: `src/gui/bootstrap.py`

The composition root wires all dependencies:

```python
async def create_app(page: ft.Page) -> None:
    """Wire adapters → PipelineRunner → GUI. Called from app.py main()."""

    # 1. Load config
    config = AppConfig.load()

    # 2. Create adapters (all from src/adapters/)
    subprocess_adapter = SubprocessAdapter()
    filesystem_adapter = FilesystemAdapter()
    tool_registry = ToolRegistry.discover(config)

    # 3. Create core services
    font_resolver = FontResolver(hunter_registry, subprocess_adapter, config)
    pipeline_runner = PipelineRunner(
        font_resolver=font_resolver,
        subprocess_adapter=subprocess_adapter,
        filesystem=filesystem_adapter,
        tool_registry=tool_registry,
        config=config,
    )

    # 4. Create log bridge
    log_queue: asyncio.Queue = asyncio.Queue()
    log_bridge = GuiLogBridge(log_queue)
    # Inject bridge into structlog processor chain
    structlog.configure(processors=[..., log_bridge, ...])

    # 5. Build GUI
    dashboard = DashboardView(
        page=page,
        pipeline_runner=pipeline_runner,
        log_queue=log_queue,
        config=config,
    )
    dashboard.build()
```

---

## Boundary Rules

The following import restrictions are ENFORCED by `test_boundary.py`:

| From `src/gui/` module | MAY import | MUST NOT import |
|------------------------|------------|-----------------|
| `app.py` | `bootstrap`, `flet` | anything in `src/core/`, `src/adapters/`, `src/hunters/` |
| `bootstrap.py` | `src/core/*`, `src/adapters/*`, `src/models/*`, `src/config` | `src/hunters/*` (indirect via FontResolver) |
| `messages.py` | `dataclasses`, `datetime`, `enum` | any `src/` module |
| `log_bridge.py` | `asyncio`, `typing` | any `src/` module except `messages` |
| `screens/*.py` | `flet`, `messages`, `widgets` | `src/core/`, `src/adapters/`, `src/hunters/` |
| `widgets/*.py` | `flet`, `messages` | `src/core/`, `src/adapters/`, `src/hunters/` |
| `styles/theme.py` | `flet` | any `src/` module |

`bootstrap.py` is the ONLY module that bridges GUI ↔ core/adapters. All other GUI modules interact with the pipeline exclusively through injected interfaces and message queues.
