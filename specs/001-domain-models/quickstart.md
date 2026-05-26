# Quickstart: Domain Models Layer

**Feature**: 001-domain-models | **Date**: 2026-05-18

## Prerequisites

- Python 3.11+
- `pydantic>=2.11.0` (install via `uv add pydantic`)

## Usage

```python
from pathlib import Path
from src.models import (
    FontQuery, FontAsset, HunterResult,
    SubtitleFile, SyncResult,
    MuxJob, MuxResult,
    ToolResult,
    EpisodeStatus, EpisodeReport, PipelineReport,
)

# Create a font query
query = FontQuery(
    requested_name="Roboto",
    anime_title="My Anime",
    episode_path=Path("D:/Anime/EP01.mkv"),
)

# Create a font asset
font = FontAsset(
    name="Roboto",
    file_path=Path("D:/Entertainment/.anime_studio/font_cache/Roboto-Regular.ttf"),
    source="google_fonts",
    layer_found=3,
    cache_hit=False,
    nameids={1: "Roboto", 2: "Regular"},
)

# JSON round-trip
json_str = font.model_dump_json()
font_back = FontAsset.model_validate_json(json_str)
assert font_back == font
assert isinstance(font_back.file_path, Path)

# Frozen — raises ValidationError
try:
    font.name = "Arial"  # type: ignore
except Exception as e:
    print(f"Immutable: {e}")

# Tool result
result = ToolResult(
    tool_name="mkvmerge",
    success=True,
    exit_code=0,
    duration_ms=1234.5,
)
assert result.suggestion is None

# Pipeline report
from datetime import datetime, timezone
report = PipelineReport(
    run_timestamp=datetime.now(timezone.utc),
    duration_ms=45000.0,
    anime_title="My Anime",
    episodes=[],
    total_fonts_found=5,
)
```

## File Layout

```text
src/models/
├── __init__.py      # Re-exports all public models
├── _types.py        # PosixPath type alias
├── font.py          # FontQuery, FontAsset, HunterResult
├── subtitle.py      # SubtitleFile, SyncResult
├── mux.py           # MuxJob, MuxResult
├── tool_result.py   # ToolResult
└── report.py        # EpisodeStatus, EpisodeReport, PipelineReport
```

## Key Patterns

1. **All models frozen** — no mutation after construction
2. **Path fields serialize as POSIX** — cross-platform JSON portability
3. **Zero I/O** — models import only from stdlib + pydantic
4. **Pydantic v2 API** — use `model_dump_json()` / `model_validate_json()` for serialization
