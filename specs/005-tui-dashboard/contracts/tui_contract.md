# TUI Interface Contract

**Feature**: 005-tui-dashboard | **Date**: 2026-05-26

## Contract: TUI ↔ PipelineRunner

The TUI is a pure consumer. It calls exactly one method:

```python
async def PipelineRunner.run(pipeline_config: PipelineConfig) -> PipelineReport
```

### Input Contract

TUI constructs `PipelineConfig` from user input:

```python
PipelineConfig(
    library_path=Path(user_input_path),
    dry_run=dry_run_checkbox_state,
    sync_enabled=False,  # hardcoded for now; future toggle
    anime_title=None,    # auto-detected by scanner
)
```

### Output Contract

TUI receives `PipelineReport` and renders:

- `report.episodes` → per-episode status rows
- `report.total_fonts_found` → font statistics
- `report.genuine_misses` → missing font list
- `report.duration_ms` → formatted duration
- `report.anime_title` → header text

### Progress Contract (Implicit — via structlog)

TUI observes progress through structlog events. No explicit API.

Events the TUI processor listens for:

| Event Key | Stage | Determinate? |
|-----------|-------|-------------|
| `library_scan_started` | scan | No (spinner) |
| `library_scan_complete` | scan | N/A (done) |
| `episode_analysis_started` | analysis | Yes (i/N) |
| `episode_mux_started` | mux | Yes (i/N) |
| `episode_mux_complete` | mux | Yes (i/N) |
| `pipeline_complete` | done | N/A |

### Error Contract

All errors from PipelineRunner are subclasses of `AnimeStudioError`. TUI catches at the worker boundary and maps:

| Error Type | TUI Presentation |
|-----------|-----------------|
| `ToolNotFoundError` | Modal dialog with install instructions |
| `ToolExecutionError` | Toast notification with suggestion |
| `FontMatchError` | Inline in results summary |
| `ConfigurationError` | Modal dialog at startup |
| `EncodingRepairError` | Toast notification |
| `MuxIntegrityError` | Toast notification |
| `HunterError` | Toast notification |

### Forbidden Imports (Hexagonal Boundary)

TUI layer (`src/tui/**`) MUST NOT import:

- `src/adapters/*`
- `src/hunters/*`
- `subprocess`, `asyncio.create_subprocess_exec`
- `httpx`
- `os.path`, `shutil`
- `open()` for file I/O

TUI MAY import:

- `src/models/*` (read-only data types)
- `src/core/pipeline_runner.PipelineRunner` (the orchestrator)
- `src/errors.*` (for error type matching)
- `src/config.AppConfig` (for bootstrap)
