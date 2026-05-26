# Data Model: Domain Models Layer

**Feature**: 001-domain-models | **Date**: 2026-05-18

## Shared Types

### `_types.py`

```python
from pathlib import Path
from typing import Annotated
from pydantic import PlainSerializer

PosixPath = Annotated[Path, PlainSerializer(lambda p: p.as_posix(), return_type=str)]
"""Path that serializes to POSIX format (forward slashes) for cross-platform JSON portability."""
```

---

## Entity: FontQuery

**File**: `src/models/font.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `requested_name` | `str` | `min_length=1` | required | Font family name to search for |
| `anime_title` | `str` | `min_length=1` | required | Anime title scoping the search |
| `episode_path` | `PosixPath` | — | required | Path to episode file |

**Relationships**: Referenced by `HunterResult.query`

---

## Entity: FontAsset

**File**: `src/models/font.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `name` | `str` | `min_length=1` (FR-019) | required | Font family name |
| `file_path` | `PosixPath` | — | required | Resolved path to font file |
| `source` | `str` | — | required | Acquisition source identifier |
| `layer_found` | `int` | `ge=0, le=6` (FR-018) | required | Search layer that found this font (0=cache, 6=last resort) |
| `cache_hit` | `bool` | — | required | Whether font was served from cache |
| `nameids` | `dict[int, str]` | — | required | OpenType name ID → string mapping |
| `is_patched` | `bool` | — | `False` | Whether font was patched/repaired |
| `patch_reason` | `str \| None` | — | `None` | Reason for patching, if applicable |

**Relationships**: Referenced by `MuxJob.fonts`, `HunterResult.font_asset`

**Validation rules**:
- `name` rejects empty string
- `layer_found` range 0-6 enforced by Pydantic `Field(ge=0, le=6)`

---

## Entity: HunterResult

**File**: `src/models/font.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `query` | `FontQuery` | — | required | Original search query |
| `font_asset` | `FontAsset \| None` | — | `None` | Resolved font, if found |
| `success` | `bool` | — | required | Whether search succeeded |
| `hunter_name` | `str` | — | required | Name of hunter that produced result |
| `duration_ms` | `float` | `ge=0` | required | Search duration in milliseconds |
| `attempts` | `int` | `ge=1` | required | Number of attempts made |

**Relationships**: Contains `FontQuery`, optionally contains `FontAsset`

---

## Entity: SubtitleFile

**File**: `src/models/subtitle.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `path` | `PosixPath` | — | required | Path to subtitle file |
| `encoding_detected` | `str` | — | required | Detected encoding (e.g., `cp1252`, `utf-8`) |
| `encoding_source` | `str` | — | required | Detection library used (e.g., `charset_normalizer`) |
| `line_ending` | `str` | — | required | Detected line ending (`\r\n`, `\n`) |
| `fonts_required` | `list[str]` | — | required | Font family names referenced in subtitle |
| `is_repaired` | `bool` | — | `False` | Whether encoding repair was applied |

**Relationships**: Referenced by `EpisodeReport.subtitle_result` (conceptually)

---

## Entity: SyncResult

**File**: `src/models/subtitle.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `success` | `bool` | — | required | Whether sync succeeded |
| `tool_used` | `str` | — | required | Primary tool used (`alass`, `ffsubsync`) |
| `tool_fallback_used` | `str \| None` | — | `None` | Fallback tool, if primary failed |
| `offset_ms` | `float` | — | required | Timing offset applied in milliseconds |
| `duration_ms` | `float` | `ge=0` | required | Sync operation duration |

---

## Entity: MuxJob

**File**: `src/models/mux.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `episode_path` | `PosixPath` | — | required | Path to source episode |
| `subtitle_path` | `PosixPath` | — | required | Path to subtitle file |
| `fonts` | `list[FontAsset]` | — | required | Fonts to attach (may be empty) |
| `dry_run` | `bool` | — | `False` | Whether this is a dry-run (no file writes) |
| `output_path` | `PosixPath` | — | required | Target output MKV path |

**Relationships**: Contains list of `FontAsset`

---

## Entity: MuxResult

**File**: `src/models/mux.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `success` | `bool` | — | required | Whether muxing succeeded |
| `output_path` | `PosixPath` | — | required | Path to output MKV |
| `duration_ms` | `float` | `ge=0` | required | Mux duration in milliseconds |
| `fonts_attached` | `int` | `ge=0` | required | Number of fonts attached |
| `warnings` | `list[str]` | — | `[]` | Mux warnings (non-fatal issues) |

---

## Entity: ToolResult

**File**: `src/models/tool_result.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `tool_name` | `str` | — | required | Name of external tool |
| `success` | `bool` | — | required | Whether tool execution succeeded |
| `exit_code` | `int` | — | required | Process exit code |
| `stdout` | `str` | — | `""` | Captured stdout |
| `stderr` | `str` | — | `""` | Captured stderr |
| `duration_ms` | `float` | `ge=0` | required | Execution duration in milliseconds |
| `suggestion` | `str \| None` | — | `None` | Human-readable remediation hint |

---

## Enum: EpisodeStatus

**File**: `src/models/report.py`

```python
class EpisodeStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
```

---

## Entity: EpisodeReport

**File**: `src/models/report.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `episode_path` | `PosixPath` | — | required | Path to episode |
| `status` | `EpisodeStatus` | — | required | Episode pipeline outcome |
| `subtitle_result` | `SyncResult \| None` | — | `None` | Subtitle sync result |
| `mux_result` | `MuxResult \| None` | — | `None` | Mux operation result |
| `missing_fonts` | `list[str]` | — | `[]` | Fonts that could not be found |
| `applied_rules` | `list[str]` | — | `[]` | Pipeline rules triggered |

**Relationships**: Contains `SyncResult`, `MuxResult`, references `EpisodeStatus`

---

## Entity: PipelineReport

**File**: `src/models/report.py` | **Frozen**: Yes

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `run_timestamp` | `datetime` | — | required | Pipeline run start time |
| `duration_ms` | `float` | `ge=0` | required | Total pipeline duration |
| `anime_title` | `str` | — | required | Anime being processed |
| `episodes` | `list[EpisodeReport]` | — | required | Per-episode reports |
| `total_fonts_found` | `int` | `ge=0` | required | Total unique fonts resolved |
| `genuine_misses` | `list[str]` | — | `[]` | Fonts searched but not found anywhere |

**Relationships**: Contains list of `EpisodeReport`

---

## Relationship Diagram

```
FontQuery ──────────┐
                    ▼
              HunterResult
                    │
                    ▼ (optional)
FontAsset ◄─────────┘
    │
    ▼ (list)
MuxJob ──────────► MuxResult
                       │
                       ▼
SubtitleFile       EpisodeReport ◄── EpisodeStatus
    │                  │
    ▼                  ▼ (list)
SyncResult ──────► PipelineReport

ToolResult (standalone — cross-cutting)
```

## Import Graph (enforced boundaries)

```
stdlib (pathlib, datetime, enum)
    ▲
pydantic (BaseModel, ConfigDict, Field)
    ▲
src/models/_types.py (PosixPath alias)
    ▲
src/models/font.py
src/models/subtitle.py
src/models/mux.py          ← imports FontAsset from font.py
src/models/tool_result.py
src/models/report.py       ← imports SyncResult, MuxResult, EpisodeStatus
    ▲
src/models/__init__.py      ← re-exports all public names
```

No imports from `core/`, `adapters/`, `hunters/`, or `tui/` — FR-015 enforced.
