# Contract: Pipeline Port

**Feature**: 004-pipeline | **Date**: 2026-05-26

## FilesystemPort

**Module**: `src/ports/filesystem.py`

Protocol for filesystem operations needed by the pipeline.

```python
@runtime_checkable
class FilesystemPort(Protocol):
    async def move_to_trash(
        self,
        source: Path,
        trash_receipt: TrashReceipt,
    ) -> None:
        """Move source file to trash directory per receipt. Create trash dir if needed."""
        ...

    async def write_file_atomic(
        self,
        target: Path,
        content: str,
        encoding: str = "utf-8",
    ) -> None:
        """Write content to target via temp file + atomic rename."""
        ...

    async def ensure_directory(self, path: Path) -> None:
        """Create directory and parents if needed."""
        ...
```

## MkvmergePort

**Module**: `src/ports/mkvmerge.py` (or inline in adapters — YAGNI decision)

Not a separate port — MkvmergeAdapter consumes `SubprocessPort` directly. Constitution XII: single implementation, no premature interface.

## Sync Adapters

Alass and Ffsubsync adapters consume `SubprocessPort`. No separate port — YAGNI. Each adapter exposes:

```python
class AlassAdapter:
    async def sync(
        self,
        reference_mkv: Path,
        subtitle_ass: Path,
        output_ass: Path,
        timeout: float = 120.0,
    ) -> ToolResult: ...

class FfsubsyncAdapter:
    async def sync(
        self,
        reference_mkv: Path,
        subtitle_ass: Path,
        output_ass: Path,
        timeout: float = 120.0,
    ) -> ToolResult: ...
```

## PipelineRunner Contract

**Module**: `src/core/pipeline_runner.py`

Core orchestrator. NOT a Protocol — concrete implementation.

```python
class PipelineRunner:
    def __init__(
        self,
        font_resolver: FontResolver,
        subprocess_adapter: SubprocessPort,
        filesystem: FilesystemPort,
        tool_registry: ToolRegistry,
        config: AppConfig,
    ) -> None: ...

    async def run(self, pipeline_config: PipelineConfig) -> PipelineReport: ...
```

## LibraryScanner Contract

**Module**: `src/core/library_scanner.py`

Stateless function, not a class.

```python
async def scan_library(library_path: Path) -> list[LibraryScanResult]: ...
```

## ReportWriter Contract

**Module**: `src/core/report_writer.py`

Stateless functions for report rendering.

```python
def render_report(report: PipelineReport) -> str:
    """Render PipelineReport to markdown string."""
    ...

def render_incremental_section(report: PipelineReport) -> str:
    """Render a delimited section for appending to existing report."""
    ...
```
