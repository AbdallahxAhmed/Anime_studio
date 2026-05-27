# Research: Embedded Subtitle Extraction

**Feature**: Embedded Subtitle Extraction via mkvextract
**Date**: 2026-05-27
**Status**: Complete

## R1: mkvextract CLI Invocation

**Decision**: `mkvextract tracks <mkv_path> <track_id>:<output_path>`

**Rationale**: Standard MKVToolNix invocation for track extraction. For ASS/SSA subtitle tracks, the output is a standalone `.ass` file with all formatting preserved. The `track_id` is the 0-based ID from `mkvmerge -J` output's `"id"` field.

**Alternatives considered**:
| Alternative | Why Rejected |
|-------------|-------------|
| `ffmpeg -map 0:s:0` | May not preserve ASS Advanced SubStation Alpha styling/formatting faithfully |
| `pymkv` Python library | Adds new dependency, violates Constitution XI (Dependency Isolation). `mkvextract` is already a CRITICAL binary. |
| Parse raw MKV container in Python | Massive complexity for zero benefit over `mkvextract` |

**Exit code semantics**:
- `0` = success
- `1` = warning (non-fatal)  
- `2` = error

This is identical to `mkvmerge`'s convention.

## R2: Track ID Mapping from mkvmerge -J

**Decision**: Use `track["id"]` (0-based integer) from `mkvmerge -J` JSON output.

**Rationale**: Confirmed from MKVToolNix documentation:
- `"id"`: 0-based track index — this is what `mkvextract` expects
- `properties.number`: 1-based track UID — NOT used for extraction
- `properties.track_name`: Human-readable name (e.g., "Arabic", "English")

**Example mkvmerge -J output** (truncated):
```json
{
  "tracks": [
    {
      "id": 0,
      "type": "video",
      "codec": "AVC/H.264/MPEG-4p10"
    },
    {
      "id": 1,
      "type": "audio",
      "codec": "AAC"
    },
    {
      "id": 2,
      "type": "subtitles",
      "codec": "SubStationAlpha",
      "properties": {
        "codec_id": "S_TEXT/ASS",
        "language": "ara",
        "language_ietf": "ar",
        "default_track": true,
        "number": 3,
        "track_name": "Arabic"
      }
    },
    {
      "id": 3,
      "type": "subtitles",
      "codec": "SubStationAlpha",
      "properties": {
        "codec_id": "S_TEXT/ASS",
        "language": "eng",
        "language_ietf": "en",
        "default_track": false,
        "number": 4,
        "track_name": "English"
      }
    }
  ]
}
```

Extraction command for Arabic track: `mkvextract tracks file.mkv 2:output.ass`

## R3: Language Tag Format

**Decision**: Support both `language` (ISO 639-2/B, e.g., `"ara"`, `"eng"`) and `language_ietf` (BCP 47, e.g., `"ar"`, `"en"`). Config uses ISO 639-2/B format.

**Rationale**: MKVToolNix v67+ added `language_ietf` (BCP 47), but many older MKV files only have the 3-letter `language` tag. The config default of `"ara"` matches ISO 639-2/B which is the most common tagging in anime community releases.

Track selection compares the user's `preferred_language` against both `language` and `language_ietf` fields:
- User sets `preferred_language = "ara"` → matches `language: "ara"` ✓
- User sets `preferred_language = "ar"` → matches `language_ietf: "ar"` ✓
- User sets `preferred_language = "eng"` → matches `language: "eng"` ✓

## R4: Config Section Design

**Decision**: Add `[subtitle]` section to TOML with two fields.

**Rationale**: Keeping subtitle-specific config separate from `[app]` follows TOML best practices (semantic grouping) and leaves room for future subtitle-related config (e.g., `fallback_language`, `extract_fonts`).

```toml
[subtitle]
preferred_language = "ara"
strict_language = true
```

**Field semantics**:
- `preferred_language` (str, default `"ara"`): ISO 639-2/B language code to prefer when selecting embedded tracks
- `strict_language` (bool, default `true`): When `true`, episodes without a matching language track are skipped entirely. When `false`, the system falls back to the default track or the first available ASS track.

## R5: Extracted File Placement

**Decision**: Use `.anime_studio_trash/EXP-YYYY-MM-DD-<filename>.tmp.ass` format.

**Rationale**: Reuses the existing `TrashReceipt` naming convention from `SubtitleFile.plan_trash_disposal()`. The `EXP-` prefix ensures automatic cleanup by the trash janitor. The `.tmp.ass` suffix signals it's a temporary extraction artifact.

**Example**: For `[SubsPlease] Frieren - 01 [1080p].mkv` extracted on 2026-05-27 with 30-day retention:
```
.anime_studio_trash/EXP-2026-06-26-[SubsPlease] Frieren - 01 [1080p].tmp.ass
```

## R6: Backward Compatibility

**Decision**: `MkvextractPort` parameter in `PipelineRunner.__init__()` is optional (`None` default).

**Rationale**: This ensures:
- Existing callers constructing `PipelineRunner` without `mkvextract_adapter` continue to work
- Tests that don't need extraction aren't forced to mock it
- If `mkvextract` binary is somehow missing at runtime, the system degrades gracefully to the old skip behavior

## R7: FilesystemPort.ensure_directory

**Decision**: Check if `ensure_directory` exists on `FilesystemPort`. If not, add it.

**Finding**: Current `FilesystemPort` has `write_file_atomic`, `move_to_trash`, `replace_file`. Need to verify if `ensure_directory` exists or needs to be added.

**Resolution**: Will add `ensure_directory(path: Path) -> None` to both port and adapter if missing. Implementation uses `asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)`.
