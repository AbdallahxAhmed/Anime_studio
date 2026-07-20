# Implementation Plan: Complete Font Hunter Chain (Phase 6.6)

**Branch**: `008-font-hunter-chain` | **Date**: 2026-06-06 | **Spec**: [spec.md](specs/008-font-hunter-chain/spec.md)

**Input**: Feature specification from `specs/008-font-hunter-chain/spec.md`

## Summary

Phase 6.5 confirmed `SystemFontHunter` works but revealed only Layer 3 is registered. Layers 1, 2, 4, 5 have no hunter classes. This plan builds the complete font resolution chain: MkvExtract (Layer 1), SiblingFont (Layer 2), six repository hunters (Layer 4), SearchEngine (Layer 5), registers all in `bootstrap.py`, removes FuzzyMatch documentation references, and updates the error behavior to never substitute fonts.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `httpx` (async HTTP), `fonttools` (font verification), `structlog` (logging), `pydantic` (models)

**Storage**: Downloaded fonts → `font_cache/` via `FontCache.store()`. System fonts resolve in-place (`is_cacheable=False`).

**Testing**: `pytest` + `pytest-asyncio`

**Target Platform**: Windows-first (cross-platform)

**Project Type**: Desktop app (PySide6 GUI, Hexagonal Architecture)

**Constraints**: httpx async only, proxy-aware, circuit breaker per source (3 failures → skip), `asyncio.sleep()` for rate limiting, fontTools verification after every download

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Hexagonal Architecture | ✅ PASS | All hunters in `src/hunters/sources/`. Each implements `HunterProtocol` from `src/ports/`. No GUI/adapter imports. |
| II. Cross-Platform | ✅ PASS | All paths via `pathlib.Path`. No Windows-specific code in hunters. |
| III. Async-First I/O | ✅ PASS | All HTTP via `httpx.AsyncClient`. File reads via `asyncio.to_thread()`. Rate limiting via `asyncio.sleep()`. |
| IV. Structured Error Handling | ✅ PASS | Hunters raise `HunterError`. FontResolver catches and continues chain. Final exhaustion logs ERROR. |
| V. Plugin Registry | ✅ PASS | All hunters registered via `HunterRegistry.register()`. Open/Closed principle maintained. |
| VII. Subprocess Lifecycle | ✅ PASS | MkvExtractHunter uses `SubprocessPort` with timeout. |
| IX. Observability | ✅ PASS | structlog events for each hunter search/download/failure. |
| XI. Dependency Isolation | ✅ PASS | No new Python dependencies. httpx, fonttools already approved. |
| XII. Simplicity & YAGNI | ✅ PASS | Each hunter is a simple class. No over-abstraction. |

## Project Structure

### Documentation (this feature)

```text
specs/008-font-hunter-chain/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
src/
├── hunters/
│   ├── __init__.py              # [MODIFY] Export new hunters
│   ├── registry.py              # [NO CHANGE]
│   ├── system_font_hunter.py    # [MODIFY] priority 4→3
│   └── sources/                 # [NEW DIR]
│       ├── __init__.py          # [NEW]
│       ├── mkv_extract.py       # [NEW] Layer 1 — MkvExtractHunter
│       ├── sibling_font.py      # [NEW] Layer 2 — SiblingFontHunter
│       ├── google_fonts.py      # [NEW] Layer 4 — GoogleFontsHunter
│       ├── fontsquirrel.py      # [NEW] Layer 4 — FontSquirrelHunter
│       ├── dafont.py            # [NEW] Layer 4 — DaFontHunter
│       ├── fontspace.py         # [NEW] Layer 4 — FontSpaceHunter
│       ├── befonts.py           # [NEW] Layer 4 — BeFontsHunter
│       ├── arabic_fonts.py      # [NEW] Layer 4 — ArabicFontsHunter
│       └── search_engine.py     # [NEW] Layer 5 — SearchEngineHunter
├── gui/
│   └── bootstrap.py             # [MODIFY] Register all hunters
├── core/
│   └── font_resolver.py         # [MODIFY] Update error message

tests/
├── unit/
│   └── hunters/
│       └── sources/
│           ├── test_mkv_extract.py       # [NEW]
│           ├── test_sibling_font.py      # [NEW]
│           ├── test_google_fonts.py      # [NEW]
│           ├── test_fontsquirrel.py      # [NEW]
│           ├── test_dafont.py            # [NEW]
│           ├── test_fontspace.py         # [NEW]
│           ├── test_befonts.py           # [NEW]
│           ├── test_arabic_fonts.py      # [NEW]
│           └── test_search_engine.py     # [NEW]

COMPACT_STATE.md                 # [MODIFY] Remove FuzzyMatch references
```

**Structure Decision**: All new hunters in `src/hunters/sources/` per constitution file organization. Each hunter is a self-contained module. Bootstrap registers them dynamically.

---

## Phase 0: Research

See [research.md](specs/008-font-hunter-chain/research.md) — all unknowns resolved.

---

## Phase 1: Design & Contracts

### Component 1: Base Hunter Helper

All network hunters share common patterns. Create a minimal base helper (NOT a class — a module with shared utilities) to avoid duplication:

#### [NEW] `_hunter_utils.py` — `src/hunters/sources/_hunter_utils.py`

Shared utilities for network hunters:

```python
import io
import zipfile
import structlog
from fontTools.ttLib import TTFont
from pathlib import Path

logger = structlog.get_logger()

FONT_EXTENSIONS = frozenset({".ttf", ".otf", ".ttc"})

def verify_font(data: bytes, filename: str) -> dict[int, str] | None:
    """Verify font data with fontTools. Returns nameids dict or None if invalid."""
    try:
        font = TTFont(io.BytesIO(data))
        nameids = {}
        for name_id in (1, 4, 6):
            record = font["name"].getName(name_id, 3, 1, 0x0409)
            if record:
                nameids[name_id] = record.toUnicode().strip()
        font.close()
        if nameids:
            return nameids
    except Exception as e:
        logger.debug("fontTools verification failed", filename=filename, error=str(e))
    return None

def extract_fonts_from_zip(data: bytes) -> list[tuple[str, bytes, dict[int, str]]]:
    """Extract font files from ZIP, verify each. Returns list of (filename, font_bytes, nameids)."""
    results = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if Path(name).suffix.lower() in FONT_EXTENSIONS:
                    font_bytes = zf.read(name)
                    nameids = verify_font(font_bytes, name)
                    if nameids:
                        results.append((Path(name).name, font_bytes, nameids))
    except Exception as e:
        logger.debug("ZIP extraction failed", error=str(e))
    return results

def normalize_font_name(name: str) -> str:
    """Normalize font name for comparison."""
    return name.strip().lower().replace("-", " ").replace("_", " ")

def font_name_matches(requested: str, candidate_nameids: dict[int, str]) -> bool:
    """Check if requested font name matches any nameID in candidate."""
    req = normalize_font_name(requested)
    for nid in (1, 4, 6):
        if nid in candidate_nameids:
            if normalize_font_name(candidate_nameids[nid]) == req:
                return True
    return False
```

---

### Component 2: MkvExtractHunter (Layer 1)

#### [NEW] [mkv_extract.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/mkv_extract.py)

Extracts font attachments from MKV files in the same library.

```python
class MkvExtractHunter:
    name = "MkvExtractHunter"
    priority = 1
    rate_limit = 0.0
    circuit_breaker_threshold = 3
    ping_url = None

    def __init__(self, subprocess_port, library_path: Path | None = None):
        self._subprocess_port = subprocess_port
        self._library_path = library_path
        self._scanned = False
        self._font_index: dict[str, tuple[Path, int, str]] = {}
        # Maps normalized font name → (mkv_path, attachment_id, original_name)

    def supports(self, query): return True

    async def search(self, query):
        if not self._scanned and self._library_path:
            await self._scan_library()
        # Look up by normalized name
        ...

    async def download(self, result):
        # mkvextract attachments <mkv> <id>:<temp_path>
        # Read temp file, verify with fontTools, return FontPayload
        ...

    async def _scan_library(self):
        # For each .mkv in library_path:
        #   mkvmerge -J → parse attachments
        #   Index font names by nameID from attachment metadata
        self._scanned = True
```

**Key decisions**:
- Scans library MKVs once (lazy, on first search call)
- Uses `mkvmerge -J` to identify attachments, `mkvextract attachments` to extract
- Extracted fonts are cached via `FontCache.store()` (returned as `FontPayload`)
- Accepts `SubprocessPort` for subprocess calls (hexagonal compliance)

---

### Component 3: SiblingFontHunter (Layer 2)

#### [NEW] [sibling_font.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/sibling_font.py)

Scans `Fonts/` or `fonts/` directories adjacent to the episode.

```python
class SiblingFontHunter:
    name = "SiblingFontHunter"
    priority = 2
    rate_limit = 0.0
    circuit_breaker_threshold = 3
    ping_url = None

    def supports(self, query): return True

    async def search(self, query):
        episode_dir = query.episode_path.parent
        for dir_name in ("Fonts", "fonts", "Font", "font"):
            fonts_dir = episode_dir / dir_name
            if fonts_dir.is_dir():
                # Scan for .ttf/.otf/.ttc files
                # Use fontTools to extract nameIDs
                # Match against query.requested_name
                # If match: return HunterResult with FontAsset(is_cacheable=True)
                ...
        # Also check parent dir (anime root) for Fonts/ dir
        parent_fonts = episode_dir.parent
        for dir_name in ("Fonts", "fonts"):
            ...

    async def download(self, result):
        # Read font file bytes, return FontPayload
        ...
```

**Key decisions**:
- Pure filesystem — no network
- Checks both episode-adjacent and parent-adjacent `Fonts/` dirs
- Uses `asyncio.to_thread()` for directory scanning
- `is_cacheable=True` — font is copied to cache so future runs skip this scan

---

### Component 4: GoogleFontsHunter (Layer 4)

#### [NEW] [google_fonts.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/google_fonts.py)

```python
class GoogleFontsHunter:
    name = "GoogleFontsHunter"
    priority = 4
    rate_limit = 0.5
    circuit_breaker_threshold = 3
    ping_url = "https://fonts.google.com"

    def __init__(self, proxy: str | None = None):
        self._proxy = proxy

    def supports(self, query): return True

    async def search(self, query):
        # Download ZIP: https://fonts.google.com/download?family={name}
        # If 404 → return []
        # Extract ZIP → find matching .ttf
        # Verify with fontTools
        # Return HunterResult with font_asset=None (needs download)
        ...

    async def download(self, result):
        # Already downloaded in search, return FontPayload
        ...
```

**Key decisions**:
- Uses direct download URL (no API key needed)
- ZIP download returns all weights/styles for a family
- Selects the best match from ZIP contents using fontTools nameID comparison
- `search()` does the heavy lifting (download + verify); `download()` returns cached result

---

### Component 5: FontSquirrelHunter (Layer 4)

#### [NEW] [fontsquirrel.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/fontsquirrel.py)

```python
class FontSquirrelHunter:
    name = "FontSquirrelHunter"
    priority = 4
    rate_limit = 1.0
    circuit_breaker_threshold = 3
    ping_url = "https://www.fontsquirrel.com"
```

Pattern: search HTML → find font slug → download ZIP → extract → verify.

---

### Component 6: DaFontHunter (Layer 4)

#### [NEW] [dafont.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/dafont.py)

```python
class DaFontHunter:
    name = "DaFontHunter"
    priority = 4
    rate_limit = 1.0
    circuit_breaker_threshold = 3
    ping_url = "https://www.dafont.com"
```

Pattern: search page → find download link → download ZIP → extract → verify.

---

### Component 7: FontSpaceHunter (Layer 4)

#### [NEW] [fontspace.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/fontspace.py)

```python
class FontSpaceHunter:
    name = "FontSpaceHunter"
    priority = 4
    rate_limit = 1.0
    circuit_breaker_threshold = 3
    ping_url = "https://www.fontspace.com"
```

---

### Component 8: BeFontsHunter (Layer 4)

#### [NEW] [befonts.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/befonts.py)

```python
class BeFontsHunter:
    name = "BeFontsHunter"
    priority = 4
    rate_limit = 1.0
    circuit_breaker_threshold = 3
    ping_url = "https://befonts.com"
```

---

### Component 9: ArabicFontsHunter (Layer 4)

#### [NEW] [arabic_fonts.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/arabic_fonts.py)

```python
class ArabicFontsHunter:
    name = "ArabicFontsHunter"
    priority = 4
    rate_limit = 1.0
    circuit_breaker_threshold = 3
    ping_url = "https://arbfonts.com"
```

This hunter is specialized for Arabic-script fonts common in Arabic anime fansubs.

---

### Component 10: SearchEngineHunter (Layer 5)

#### [NEW] [search_engine.py](file:///d:/Dev/projects/Anime_studio/src/hunters/sources/search_engine.py)

```python
BLOCKED_DOMAINS = frozenset({
    "pinterest.com", "facebook.com", "instagram.com",
    "youtube.com", "twitter.com", "x.com",
    "freefontsfamily.com",  # known spam/redirect
    # Add more as discovered
})

class SearchEngineHunter:
    name = "SearchEngineHunter"
    priority = 5
    rate_limit = 2.0  # Aggressive rate limit — nuclear option
    circuit_breaker_threshold = 3
    ping_url = "https://html.duckduckgo.com"

    def __init__(self, proxy: str | None = None):
        self._proxy = proxy

    def supports(self, query): return True

    async def search(self, query):
        # 1. Query: https://html.duckduckgo.com/html/?q={font_name}+font+free+download+ttf
        # 2. Parse result links (top 10)
        # 3. For each link not in BLOCKED_DOMAINS:
        #    a. Fetch page HTML
        #    b. Find direct .ttf/.otf/.ttc links or ZIP download links
        #    c. Download candidate
        #    d. Verify with fontTools
        #    e. If valid and name matches → return HunterResult
        # 4. If none found → return []
        ...

    async def download(self, result):
        # Font data already downloaded during search
        ...
```

**Key decisions**:
- DuckDuckGo `html.duckduckgo.com` for static HTML (no JS)
- Top 10 results max
- Blocked domain filtering
- Direct font file link detection via URL pattern matching (`.ttf`, `.otf`, `.zip` suffixes)
- fontTools verification before accepting any download
- High rate limit (2.0s) to avoid abuse

---

### Component 11: SystemFontHunter Priority Fix

#### [MODIFY] [system_font_hunter.py](file:///d:/Dev/projects/Anime_studio/src/hunters/system_font_hunter.py)

Change `priority: int = 4` → `priority: int = 3` to correctly position as Layer 3.

---

### Component 12: FontResolver Error Message Update

#### [MODIFY] [font_resolver.py](file:///d:/Dev/projects/Anime_studio/src/core/font_resolver.py)

Update the error message at line 96-99 to match spec FR-011:

```python
# BEFORE
error_msg = f"Font '{query.requested_name}' resolution failed after checking all layers. Audit trail: {'; '.join(audit_trail)}"

# AFTER
error_msg = f"Font '{query.requested_name}' not found on any known source. Mux will proceed without this font."
```

Keep the audit trail in the structured log but not in the error message shown to the pipeline.

---

### Component 13: Bootstrap Registration

#### [MODIFY] [bootstrap.py](file:///d:/Dev/projects/Anime_studio/src/gui/bootstrap.py)

After creating `hunter_registry` (line 114), register ALL hunters:

```python
# Layer 1: MKV Extract
from src.hunters.sources.mkv_extract import MkvExtractHunter
# Layer 2: Sibling Fonts
from src.hunters.sources.sibling_font import SiblingFontHunter
# Layer 3: System Fonts (already registered)
# Layer 4: Network repositories
from src.hunters.sources.google_fonts import GoogleFontsHunter
from src.hunters.sources.fontsquirrel import FontSquirrelHunter
from src.hunters.sources.dafont import DaFontHunter
from src.hunters.sources.fontspace import FontSpaceHunter
from src.hunters.sources.befonts import BeFontsHunter
from src.hunters.sources.arabic_fonts import ArabicFontsHunter
# Layer 5: Search engine (nuclear)
from src.hunters.sources.search_engine import SearchEngineHunter
```

**Note**: Must use `importlib.import_module()` pattern consistent with existing bootstrap style to maintain hexagonal boundaries.

---

### Component 14: Documentation Cleanup

#### [MODIFY] COMPACT_STATE.md

Remove FuzzyMatch references from lines 73 and 305. Update layer diagram:

```
[0] LocalCache       → .anime_studio/font_cache/
[1] MkvExtract       → embedded fonts from existing library MKVs
[2] SiblingScan      → Fonts/ dirs adjacent to episodes
[3] SystemFontHunter → OS system fonts, .ttc support
[4] NetworkHunters   → Google Fonts, FontSquirrel, DaFont, FontSpace, Befonts, ArabicFonts
[5] SearchEngine     → DuckDuckGo HTML search (nuclear option, last resort)
```

---

## Verification Plan

### Automated Tests

Each hunter class has its own test file under `tests/unit/hunters/sources/`. Tests mock `httpx.AsyncClient` and `SubprocessPort` — no real network calls.

```bash
# Run all unit tests
pytest tests/unit/ -v --tb=short

# Run only new hunter tests
pytest tests/unit/hunters/sources/ -v --tb=short
```

**Test coverage per hunter**:
1. `supports()` → always True
2. `search()` with mocked successful response → returns valid `HunterResult`
3. `search()` with 404/error response → returns empty list
4. `search()` with corrupt font data → fontTools rejects, returns empty list
5. `download()` with valid result → returns `FontPayload`
6. Circuit breaker integration → 3 failures → hunter skipped
7. Rate limit → `asyncio.sleep()` called with correct delay

### Manual Verification

1. Run pipeline against anime folder with ASS referencing:
   - System fonts (Arial, Segoe UI) → Layer 3 resolves
   - Popular free font (Roboto, Open Sans) → Layer 4 resolves
   - Fonts in sibling `Fonts/` dir → Layer 2 resolves
2. `mkvinfo output.mkv` → verify font attachments present
3. Check structlog output for layer-by-layer resolution trail
4. Verify no "FuzzyMatch" text in any `src/` file

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| 9 new hunter classes | Each source has different HTML/API patterns | A single "NetworkHunter" would be a god-class with switch statements |
| `_hunter_utils.py` shared module | ZIP extraction + fontTools verification repeated across 7 hunters | Inlining duplicates ~40 lines per hunter |
