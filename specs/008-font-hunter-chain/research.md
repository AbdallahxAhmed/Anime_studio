# Research: Phase 6.6 — Complete Font Hunter Chain

**Date**: 2026-06-06 | **Spec**: [spec.md](specs/008-font-hunter-chain/spec.md)

## R1: Current State of Hunter Registration

**Decision**: Only `SystemFontHunter` (Layer 3, priority=4) is registered in `bootstrap.py` line 119.

**Rationale**: Confirmed by reading [bootstrap.py](file:///d:/Dev/projects/Anime_studio/src/gui/bootstrap.py#L116-L119). The `HunterRegistry` is created and only `SystemFontHunter()` is registered. No other hunter classes exist in `src/hunters/`.

**Current state**:
- `src/hunters/` contains: `__init__.py`, `registry.py`, `system_font_hunter.py`
- `src/hunters/sources/` does NOT exist
- No MkvExtractHunter, SiblingFontHunter, or any network hunter classes exist anywhere

## R2: FuzzyMatchHunter Code Status

**Decision**: No FuzzyMatchHunter code exists in `src/`. Only documentation references in `COMPACT_STATE.md` (lines 73, 305) and old `specs/003-font-system/` artifacts.

**Rationale**: Searched entire `src/` tree. Zero hits for FuzzyMatch class. The "fuzzy" references in `src/core/library_scanner.py` (line 300, 328) are for episode-to-subtitle filename matching (SequenceMatcher), which is unrelated to font matching and should NOT be removed.

**Action**: Remove FuzzyMatch references from `COMPACT_STATE.md` layer diagram only. Library scanner fuzzy pairing is a different domain.

## R3: MkvextractAdapter Availability

**Decision**: `MkvextractAdapter` already exists at [src/adapters/mkvextract.py](file:///d:/Dev/projects/Anime_studio/src/adapters/mkvextract.py). It supports `extract_track()` for subtitle extraction. For Layer 1 font extraction, we need to use `mkvextract attachments` (different CLI syntax from `mkvextract tracks`).

**Rationale**: The existing adapter extracts subtitle tracks. Font attachment extraction uses:
```
mkvextract attachments <mkv_path> <attachment_id>:<output_path>
```
The `mkvmerge -J` identify output lists attachments with their IDs and MIME types. We need a new method or the MkvExtractHunter can call `SubprocessPort` directly.

**Alternative considered**: Extend MkvextractAdapter with `extract_attachments()`. Rejected because hunter classes should use ports, not adapters directly — and the MkvExtractHunter should own its own extraction logic via SubprocessPort.

**Decision**: MkvExtractHunter will accept a `SubprocessPort` and call `mkvextract attachments` directly, plus `MkvmergeAdapter.identify()` for track enumeration.

## R4: Google Fonts API

**Decision**: Use the Google Fonts developer API (`https://fonts.google.com/download?family=FAMILY_NAME`) for direct ZIP download. The API at `https://www.googleapis.com/webfonts/v1/webfonts?key=API_KEY` lists all families but requires an API key. Alternative: parse the google-webfonts-helper or use the GitHub mirror at `https://github.com/google/fonts`.

**Best approach**: Use `https://fonts.google.com/download?family={encoded_name}` which returns a ZIP without API key. Parse ZIP for .ttf files. Verify with fontTools.

**Ping URL**: `https://fonts.google.com` (HEAD request for health check).

## R5: FontSquirrel

**Decision**: FontSquirrel has no public API. Use HTML scraping: `https://www.fontsquirrel.com/fonts/list/find_fonts?q={font_name}` returns search results HTML. Individual font download pages at `https://www.fontsquirrel.com/fonts/download/{font_slug}` return ZIP.

**Ping URL**: `https://www.fontsquirrel.com`

## R6: DaFont

**Decision**: DaFont has no API. Search via `https://www.dafont.com/search.php?q={font_name}`. Download links are on individual font pages. HTML parsing required.

**Ping URL**: `https://www.dafont.com`

## R7: FontSpace

**Decision**: FontSpace search: `https://www.fontspace.com/search?q={font_name}`. Downloads are on individual pages. HTML scraping required.

**Ping URL**: `https://www.fontspace.com`

## R8: DuckDuckGo HTML Search

**Decision**: Use `https://html.duckduckgo.com/html/?q={query}` which returns static HTML (no JS required). Parse `<a class="result__a">` links. This is the most reliable non-JS search endpoint.

**Rate limiting**: 1.0s between requests to avoid rate limiting.

## R9: Blocked Domain List for SearchEngineHunter

**Decision**: Maintain a static frozenset of known spam/malware domains in `src/hunters/sources/search_engine.py`. Initial list from common font-spam sites. User can extend via config in future versions.

## R10: Priority Numbering

**Decision**: Current `SystemFontHunter.priority = 4`. The `FontResolver` iterates hunters sorted by ascending priority. Need to assign:
- Layer 0: FontCache (handled separately in resolver, not a hunter)
- Layer 1: MkvExtractHunter → priority = 1
- Layer 2: SiblingFontHunter → priority = 2
- Layer 3: SystemFontHunter → priority = 4 (already set, maps to Layer 3 in user's numbering)
- Layer 4: All repository hunters → priority = 5 (sub-ordered by specificity)
- Layer 5: SearchEngineHunter → priority = 6

Wait — the `FontAsset.layer_found` has `le=6` constraint. Priority values map to layers. Let me re-examine:

Current SystemFontHunter has `priority: int = 4`. In the constitution it says "Layer 3 (between sibling-scan and network hunters)". The `layer_found` field max is 6.

**Revised priority mapping**:
| Layer | Hunter | priority | layer_found |
|-------|--------|----------|-------------|
| 1 | MkvExtractHunter | 1 | 1 |
| 2 | SiblingFontHunter | 2 | 2 |
| 3 | SystemFontHunter | 3 | 3 |
| 4 | GoogleFontsHunter | 4 | 4 |
| 4 | FontSquirrelHunter | 4 | 4 |
| 4 | DaFontHunter | 4 | 4 |
| 4 | FontSpaceHunter | 4 | 4 |
| 4 | BeFontsHunter | 4 | 4 |
| 4 | ArabicFontsHunter | 4 | 4 |
| 5 | SearchEngineHunter | 5 | 5 |

**BREAKING**: SystemFontHunter currently has `priority = 4`. Needs change to `3`. This is a one-line change.

## R11: Befonts and Arabic Font Sites

**Decision**:
- Befonts: `https://befonts.com/?s={font_name}` — search page with download links
- Arabic fonts: `https://arbfonts.com/` (common Arabic font repository). Search + download.

Both require HTML scraping. Lower priority than Google Fonts.
