# Quickstart: Embedded Subtitle Extraction

## What Changed

The pipeline now extracts embedded ASS subtitle tracks from MKV files instead of skipping them. When an MKV has no external `.ass` sibling, the system:

1. Identifies embedded ASS tracks via `mkvmerge -J`
2. Selects the best track based on your language preference
3. Extracts it to a temp file via `mkvextract`
4. Feeds it through the normal repair → sync → font resolve → mux pipeline

## Configuration

Add a `[subtitle]` section to your `config.toml`:

```toml
[subtitle]
preferred_language = "ara"    # ISO 639-2/B language code
strict_language = true        # Skip episodes without matching language
```

**Language codes**: `"ara"` (Arabic), `"eng"` (English), `"jpn"` (Japanese), `"fre"` (French), etc.

**Strict mode**:
- `true` (default): Only extract tracks matching your preferred language. Episodes without a match are skipped with a clear warning.
- `false`: Falls back to the default track or first available ASS track when preferred language is missing.

## Behavior

| Scenario | strict=true | strict=false |
|----------|-------------|--------------|
| Preferred language found | ✅ Extract & process | ✅ Extract & process |
| No preferred, has other ASS tracks | ⚠️ Skip + warning | ✅ Extract default/first |
| No ASS tracks at all | ⚠️ Skip | ⚠️ Skip |
| mkvextract not available | ⚠️ Skip (old behavior) | ⚠️ Skip (old behavior) |

## Prerequisites

- `mkvextract` (part of MKVToolNix) must be installed — it's already a CRITICAL dependency
- Install via Scoop: `scoop install mkvtoolnix`
