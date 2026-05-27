# Implementation Plan: Embedded Subtitle Extraction via mkvextract

**Branch**: `008-font-ingestion` | **Date**: 2026-05-27 | **Spec**: [spec.md](specs/007-font-ingestion/spec.md)

**Input**: User requirement: "Implement Embedded Subtitle Extraction using mkvextract with configurable language preferences."

## Summary

Currently, MKV episodes with only embedded subtitles (no external `.ass` sibling) are detected by the `LibraryScanner` but **skipped** in the pipeline with a log message "skipping embedded-only episode." This plan adds the ability to **extract** a preferred embedded ASS track via `mkvextract`, apply language preferences from config, and feed the extracted subtitle into the existing repair/analysis/mux pipeline — transforming previously dead-end episodes into fully processable ones.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `pydantic` (models), `structlog` (logging), `asyncio` (subprocess), `mkvextract` (MKVToolNix CLI — already CRITICAL in `DependencyChecker`)

**Storage**: Extracted temp files go to `.anime_studio_trash/` per existing trash conventions

**Testing**: `pytest` + `pytest-asyncio`

**Target Platform**: Windows-first (cross-platform)

**Project Type**: Desktop app (Hexagonal Architecture)

**Constraints**: No direct subprocess calls in Core layer; all I/O through ports/adapters

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Hexagonal Architecture | ✅ PASS | New `MkvextractPort` (port) + `MkvextractAdapter` (adapter). Core uses only the port. |
| II. Cross-Platform | ✅ PASS | All paths via `pathlib.Path`. Binary resolved via `shutil.which()` + `ToolRegistry`. |
| III. Async-First I/O | ✅ PASS | `mkvextract` invoked via `SubprocessPort.execute()` (async). Disk semaphore honoured. |
| IV. Structured Error Handling | ✅ PASS | Returns `ToolResult`. Domain errors for failed extraction. |
| VI. Data Safety | ✅ PASS | Extracted file written to `.anime_studio_trash/` with `EXP-` prefix (TrashReceipt naming). |
| VII. Subprocess Lifecycle | ✅ PASS | Timeout enforcement via `SubprocessPort`. |
| IX. Observability | ✅ PASS | `structlog` events for extraction start/complete/skip. |
| XI. Dependency Isolation | ✅ PASS | `mkvextract` already in `DEFAULT_SPECS` as CRITICAL. No new Python deps. |
| XII. Simplicity & YAGNI | ✅ PASS | `MkvextractPort` has one implementation — justified because it's a distinct binary with a distinct invocation pattern (not mkvmerge). |

## Project Structure

### Documentation (this feature)

```text
specs/007-font-ingestion/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/           # Phase 1 output
```

### Source Code (repository root)

```text
src/
├── config.py            # [MODIFY] Add SubtitleConfig nested model
├── models/
│   ├── __init__.py      # [MODIFY] Export new model
│   └── pipeline.py      # [MODIFY] Redesign EmbeddedSubInfo with EmbeddedTrack
├── ports/
│   ├── __init__.py      # [MODIFY] Export MkvextractPort
│   └── mkvextract.py    # [NEW] MkvextractPort protocol
├── adapters/
│   ├── __init__.py      # [MODIFY] Export MkvextractAdapter
│   └── mkvextract.py    # [NEW] MkvextractAdapter implementation
├── core/
│   ├── library_scanner.py  # [MODIFY] Update _parse_embedded_info to populate EmbeddedTrack
│   └── pipeline_runner.py  # [MODIFY] Replace EMBEDDED skip logic with extraction logic

tests/
├── unit/
│   ├── models/
│   │   └── test_pipeline.py    # [MODIFY] Tests for EmbeddedTrack + EmbeddedSubInfo
│   ├── adapters/
│   │   └── test_mkvextract.py  # [NEW] Unit tests for MkvextractAdapter
│   ├── core/
│   │   ├── test_library_scanner.py  # [MODIFY] Test updated _parse_embedded_info
│   │   └── test_pipeline_runner.py  # [MODIFY] Test embedded extraction flow
│   └── test_config.py         # [MODIFY] Test SubtitleConfig loading
```

**Structure Decision**: Follows existing hexagonal pattern exactly. New port+adapter pair for `mkvextract` (parallel to `MkvmergePort`/`MkvmergeAdapter`). Config extended with a nested `[subtitle]` section.

---

## Phase 0: Research

### R1: mkvextract CLI Invocation Pattern

**Decision**: Use `mkvextract tracks <mkv_path> <track_id>:<output_path>` syntax.

**Rationale**: This is the documented mkvextract invocation for track extraction. It extracts a single track by its ID (the integer from `mkvmerge -J` output `properties.number - 1`, which is the 0-based track ID). For ASS/SSA tracks, the output is a standalone `.ass` file.

**Alternatives considered**:
- `mkvextract tracks <mkv_path> <track_id>:<output>` — chosen, standard approach
- Piping through ffmpeg `-map 0:s:0` — rejected: ffmpeg may not preserve ASS styling faithfully
- Using `pymkv` Python library — rejected: adds new dependency, violates XI (Dependency Isolation)

### R2: Track ID Mapping from mkvmerge -J

**Decision**: The track ID for `mkvextract` comes from `track["id"]` in the `mkvmerge -J` JSON output (0-based). This is **not** `properties.number` (which is 1-based and refers to the track UID).

**Rationale**: Confirmed from MKVToolNix documentation. The `"id"` field is what `mkvextract` expects.

### R3: Language Tag Format

**Decision**: Use the `language_ietf` property from `mkvmerge -J` when available (e.g., `"ar"`, `"en"`), falling back to `language` (e.g., `"ara"`, `"eng"` ISO 639-2/B format). The user-facing config uses ISO 639-2/B (`"ara"`) for consistency with how MKVToolNix historically tagged tracks.

**Rationale**: MKVToolNix v67+ added `language_ietf` (BCP 47), but many older files only have the 3-letter `language` tag. Supporting both maximizes compatibility.

### R4: Config Section Naming

**Decision**: Add `[subtitle]` section to `config.toml` with `preferred_language` (default `"ara"`) and `strict_language` (default `true`).

**Rationale**: Matches the user's requirement. The `"ara"` default reflects Arabic anime fansub community use case per constitution (Section VIII).

---

## Phase 1: Design & Data Models

### Component 1: Config Update

#### [MODIFY] [config.py](file:///d:/Dev/projects/Anime_studio/src/config.py)

Add a `SubtitleConfig` nested model and incorporate it into `AppConfig`:

```python
class SubtitleConfig(BaseModel):
    preferred_language: str = "ara"
    strict_language: bool = True

class AppConfig(BaseModel):
    # ... existing fields ...
    subtitle: SubtitleConfig = SubtitleConfig()
```

The `save_to_toml()` and `load_from_toml()` methods need to handle the nested `[subtitle]` section. The TOML structure becomes:

```toml
[app]
max_concurrent_disk_io = 4
# ...

[subtitle]
preferred_language = "ara"
strict_language = true
```

The `load_from_toml()` must check for both `data.get("subtitle")` and fallback to defaults. `save_to_toml()` must emit the `[subtitle]` section separately.

---

### Component 2: Model Update — EmbeddedTrack

#### [MODIFY] [pipeline.py](file:///d:/Dev/projects/Anime_studio/src/models/pipeline.py)

Introduce `EmbeddedTrack` and update `EmbeddedSubInfo`:

```python
class EmbeddedTrack(BaseModel):
    """One embedded ASS/SSA subtitle track inside an MKV."""
    model_config = ConfigDict(frozen=True)

    track_id: int = Field(ge=0)
    language: str = ""          # ISO 639-2/B e.g. "ara", "eng"
    language_ietf: str = ""     # BCP 47 e.g. "ar", "en"  
    is_default: bool = False
    codec: str = ""             # e.g. "SubStationAlpha"

class EmbeddedSubInfo(BaseModel):
    """Metadata about embedded ASS subtitle tracks inside an MKV container."""
    model_config = ConfigDict(frozen=True)

    tracks: list[EmbeddedTrack] = Field(default_factory=list)
    has_embedded_fonts: bool = False
    embedded_font_names: list[str] = Field(default_factory=list)

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def languages(self) -> list[str]:
        return [t.language for t in self.tracks if t.language]
```

> [!IMPORTANT]
> **Breaking change**: `EmbeddedSubInfo.track_count` changes from `Field(ge=1)` to a computed property. `languages` becomes a computed property. Downstream code reading `embedded_sub_info.track_count` or `.languages` is unaffected (attribute access is identical), but Pydantic serialization changes. Callers constructing `EmbeddedSubInfo(track_count=..., languages=...)` must be updated to use `tracks=[...]` instead.

---

### Component 3: New Port — MkvextractPort

#### [NEW] [mkvextract.py](file:///d:/Dev/projects/Anime_studio/src/ports/mkvextract.py)

```python
from typing import Protocol, runtime_checkable
from pathlib import Path
from src.models.tool_result import ToolResult


@runtime_checkable
class MkvextractPort(Protocol):
    async def extract_track(
        self,
        mkv_path: Path,
        track_id: int,
        output_path: Path,
        timeout: float = 120.0,
    ) -> ToolResult:
        """Extract a single track from an MKV file via mkvextract.

        Args:
            mkv_path: Path to the source MKV file.
            track_id: 0-based track ID (from mkvmerge -J "id" field).
            output_path: Path to write the extracted track to.
            timeout: Timeout in seconds.

        Returns:
            ToolResult describing the extraction outcome.
        """
        ...
```

---

### Component 4: New Adapter — MkvextractAdapter

#### [NEW] [mkvextract.py](file:///d:/Dev/projects/Anime_studio/src/adapters/mkvextract.py)

```python
from pathlib import Path
import structlog
from src.ports.subprocess import SubprocessPort
from src.models.tool_result import ToolResult

logger = structlog.get_logger()


class MkvextractAdapter:
    def __init__(self, subprocess_port: SubprocessPort) -> None:
        self.subprocess_port = subprocess_port

    async def extract_track(
        self,
        mkv_path: Path,
        track_id: int,
        output_path: Path,
        timeout: float = 120.0,
    ) -> ToolResult:
        """Extract a single track from an MKV container."""
        args = [
            "mkvextract",
            "tracks",
            str(mkv_path),
            f"{track_id}:{output_path}",
        ]

        logger.info(
            "extracting embedded subtitle track",
            mkv=mkv_path.name,
            track_id=track_id,
            output=str(output_path),
        )

        result = await self.subprocess_port.execute(args, timeout=timeout)

        if result.success:
            logger.info(
                "subtitle track extracted successfully",
                mkv=mkv_path.name,
                track_id=track_id,
                duration_ms=result.duration_ms,
            )
        else:
            logger.error(
                "mkvextract failed",
                mkv=mkv_path.name,
                track_id=track_id,
                exit_code=result.exit_code,
                stderr=result.stderr,
            )

        return result
```

**Key design**: The adapter delegates to `SubprocessPort` (respects Hexagonal boundaries). It does **not** acquire the disk semaphore itself — that's the caller's responsibility (pipeline runner), consistent with how `MkvmergeAdapter.mux()` is called inside `async with mux_semaphore`.

---

### Component 5: Scanner Update — _parse_embedded_info

#### [MODIFY] [library_scanner.py](file:///d:/Dev/projects/Anime_studio/src/core/library_scanner.py)

Update `_parse_embedded_info()` to populate `EmbeddedTrack` objects with track IDs, languages, and default flags from the `mkvmerge -J` JSON:

```python
def _parse_embedded_info(identify_result: dict) -> EmbeddedSubInfo | None:
    tracks = identify_result.get("tracks", [])
    embedded_tracks = []
    for t in tracks:
        if t.get("type") != "subtitles":
            continue
        codec = (t.get("codec") or "").lower()
        codec_id = (t.get("properties", {}).get("codec_id") or "").lower()
        if (
            "ass" in codec
            or "substation" in codec
            or "ssa" in codec
            or "s_text/ass" in codec_id
        ):
            props = t.get("properties", {})
            embedded_tracks.append(
                EmbeddedTrack(
                    track_id=t.get("id", 0),
                    language=props.get("language", ""),
                    language_ietf=props.get("language_ietf", ""),
                    is_default=props.get("default_track", False),
                    codec=t.get("codec", ""),
                )
            )

    if not embedded_tracks:
        return None

    # Detect embedded font attachments (unchanged)
    embedded_font_names = []
    for a in identify_result.get("attachments", []):
        ct = (a.get("content_type") or "").lower()
        nm = a.get("file_name", "")
        if "font" in ct or nm.lower().endswith((".ttf", ".otf", ".ttc", ".otc")):
            embedded_font_names.append(nm)

    return EmbeddedSubInfo(
        tracks=embedded_tracks,
        has_embedded_fonts=bool(embedded_font_names),
        embedded_font_names=sorted(embedded_font_names),
    )
```

---

### Component 6: Core Pipeline Logic — Embedded Extraction

#### [MODIFY] [pipeline_runner.py](file:///d:/Dev/projects/Anime_studio/src/core/pipeline_runner.py)

This is the most significant change. The current logic (lines 122–142) unconditionally skips embedded-only episodes. The new logic:

1. **Accept `MkvextractPort`** in `PipelineRunner.__init__()` as an optional dependency
2. **Replace the skip loop** with a track evaluation + extraction step
3. **Track selection algorithm**:
   - Find tracks matching `config.subtitle.preferred_language` (compare against both `language` and `language_ietf`)
   - If multiple matches, prefer `is_default=True`, then lowest `track_id`
   - If no match and `strict_language=True`: skip episode, log WARNING
   - If no match and `strict_language=False`: pick the default track, or first available
4. **Extraction**: Call `mkvextract_adapter.extract_track()` inside `async with disk_semaphore`
5. **Output path**: `.anime_studio_trash/EXP-YYYY-MM-DD-<filename>.tmp.ass` (TrashReceipt format)
6. **Rewrite scan result**: Create a new `LibraryScanResult` with `subtitle_path` set to the extracted file and `subtitle_source` remaining `EMBEDDED`, then pass to `_analyze_episode()`

```python
# New method on PipelineRunner
def _select_track(
    self,
    info: EmbeddedSubInfo,
    preferred_language: str,
    strict: bool,
) -> EmbeddedTrack | None:
    """Select the best embedded track based on language preference."""
    # Match by language (ISO 639-2/B) or language_ietf (BCP 47)
    candidates = [
        t for t in info.tracks
        if t.language == preferred_language
        or t.language_ietf == preferred_language
    ]

    if candidates:
        # Prefer default track among candidates
        defaults = [t for t in candidates if t.is_default]
        if defaults:
            return defaults[0]
        return candidates[0]

    if strict:
        return None  # Caller will skip

    # Non-strict: pick default track or first available
    defaults = [t for t in info.tracks if t.is_default]
    if defaults:
        return defaults[0]
    return info.tracks[0] if info.tracks else None
```

The pipeline `run()` method loop changes from:

```python
# BEFORE
if scan.subtitle_source == SubtitleSource.EMBEDDED:
    logger.info("skipping embedded-only episode ...")
    embedded_only_reports.append(...)
```

To:

```python
# AFTER
if scan.subtitle_source == SubtitleSource.EMBEDDED:
    if not self.mkvextract_adapter or not scan.embedded_sub_info:
        # No extraction capability or no embedded info
        embedded_only_reports.append(...)
        continue

    selected = self._select_track(
        scan.embedded_sub_info,
        self.config.subtitle.preferred_language,
        self.config.subtitle.strict_language,
    )

    if selected is None:
        # strict mode and preferred language not found
        logger.warning(
            "skipping episode: preferred subtitle language not found",
            episode=scan.episode_path.name,
            preferred=self.config.subtitle.preferred_language,
            available=[t.language for t in scan.embedded_sub_info.tracks],
        )
        embedded_only_reports.append(...)
        continue

    # Extract track to trash-formatted temp path
    exp_date = (run_timestamp + timedelta(days=self.config.trash_max_age_days)).strftime("%Y-%m-%d")
    trash_dir = scan.episode_path.parent / ".anime_studio_trash"
    extract_path = trash_dir / f"EXP-{exp_date}-{scan.episode_path.stem}.tmp.ass"

    # Ensure trash directory exists
    await self.filesystem.ensure_directory(trash_dir)

    async with self.disk_semaphore:
        result = await self.mkvextract_adapter.extract_track(
            scan.episode_path,
            selected.track_id,
            extract_path,
            timeout=float(self.config.default_timeout_s),
        )

    if not result.success:
        logger.error(
            "embedded subtitle extraction failed",
            episode=scan.episode_path.name,
            track_id=selected.track_id,
            stderr=result.stderr,
        )
        embedded_only_reports.append(...)
        continue

    # Rewrite scan result with extracted subtitle path
    updated_scan = scan.model_copy(
        update={"subtitle_path": extract_path}
    )
    external_scans.append(updated_scan)
    logger.info(
        "embedded subtitle extracted, proceeding to analysis",
        episode=scan.episode_path.name,
        track_id=selected.track_id,
        language=selected.language,
        extract_path=str(extract_path),
    )
```

> [!IMPORTANT]
> The `mkvextract_adapter` parameter in `PipelineRunner.__init__()` is **optional** (`MkvextractPort | None = None`). When `None`, embedded episodes behave exactly as before (skip). This preserves backward compatibility and allows deployment without `mkvextract` temporarily.

---

### Component 7: FilesystemPort Update

#### [MODIFY] [filesystem.py](file:///d:/Dev/projects/Anime_studio/src/ports/filesystem.py)

Need to check if `ensure_directory` already exists. If not, add:

```python
async def ensure_directory(self, path: Path) -> None:
    """Ensure a directory exists, creating it and parents if needed."""
    ...
```

This follows the same async pattern. The `FilesystemAdapter` implementation:
```python
async def ensure_directory(self, path: Path) -> None:
    await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)
```

---

## Verification Plan

### Automated Tests

1. **Unit: `EmbeddedTrack` + `EmbeddedSubInfo`** — Test construction, computed properties, serialization
2. **Unit: `_parse_embedded_info`** — Test with mock `mkvmerge -J` JSON containing multiple tracks with various languages, default flags, and codec IDs
3. **Unit: `MkvextractAdapter.extract_track`** — Mock `SubprocessPort`, verify correct args `["mkvextract", "tracks", "<path>", "N:<out>"]`
4. **Unit: `PipelineRunner._select_track`** — Test all branches:
   - Preferred language match (single)
   - Multiple matches, prefer default
   - No match, strict=True → None
   - No match, strict=False → fallback to default/first
5. **Unit: `PipelineRunner.run` embedded flow** — Mock mkvextract adapter, verify extraction is called, subtitle_path is updated, episode proceeds through analysis
6. **Unit: Config** — Test `SubtitleConfig` loading from TOML with `[subtitle]` section, defaults when section missing

```bash
pytest tests/unit/ -v --tb=short
```

### Manual Verification

- Run pipeline against a directory with MKV files containing embedded Arabic ASS subtitles
- Verify extracted `.ass` appears in `.anime_studio_trash/` with correct naming
- Verify the episode report shows COMPLETE/PARTIAL instead of SKIPPED
- Test `strict_language = true` with a non-matching language → verify SKIPPED + warning in report

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| `MkvextractPort` has 1 impl | Distinct binary from `mkvmerge` with different CLI syntax; lumping into `MkvmergePort` would violate Single Responsibility | A combined port would force mocking both tools together in tests |
