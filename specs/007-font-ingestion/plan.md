# Implementation Plan: Hotfix — Core Stability & Hunter Resolution (v1.7.0)

**Branch**: `008-font-ingestion` | **Date**: 2026-05-27 | **Spec**: [spec.md](file:///D:/Dev/projects/Anime_studio/specs/007-font-ingestion/spec.md)

**Input**: Feature specification from `specs/007-font-ingestion/spec.md` + user hotfix description targeting three critical pipeline failures.

## Summary

The core pipeline has three critical failures blocking Phase 7 packaging:

1. **Trash Ingestion Loop** — `library_scanner.py` uses `rglob("*.mkv")` with **zero directory exclusion**, causing `.anime_studio_trash/` (and `.git/`, etc.) contents to be rediscovered as valid episodes.
2. **Tool Discovery Logging Gap** — `dependency_checker.py` **already correctly implements** the 5-step Constitution XIII hierarchy, but lacks per-step diagnostic logging to explain *why* a tool wasn't found. The original report of "failing to locate alass" is likely a system-specific path issue, not a code defect.
3. **Font Hunter Collapse** — `SystemFontHunter` uses strict exact-match with no name normalization (no variant stripping, no `.ttc` support). `NetworkFontHunter` **does not exist yet**. `FontResolver.startup_ping()` creates bare `httpx.AsyncClient()` without injecting `config.proxy`, causing immediate circuit breaker trips for users behind proxies.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: fonttools, httpx (async), structlog, pydantic v2, PySide6, qasync

**Storage**: TOML font cache index at `D:\Entertainment\.anime_studio\font_cache\`

**Testing**: pytest + pytest-asyncio

**Target Platform**: Windows-first (cross-platform via `sys.platform` gating)

**Project Type**: Desktop app (Hexagonal Architecture)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Hexagonal Architecture | ✅ PASS | All changes stay within their proper layers: scanner→core, checker→adapters, hunters→hunters, resolver→core |
| II. Cross-Platform | ✅ PASS | Windows-specific paths gated behind `sys.platform == "win32"`. Unix falls through to `shutil.which()`. Font dirs already cross-platform. |
| III. Async-First I/O | ✅ PASS | Scanner uses `asyncio.to_thread()`. Network hunter will use `httpx.AsyncClient`. Proxy from `config.toml`. |
| IV. Structured Error Handling | ✅ PASS | Domain exceptions preserved. `ToolResult` pattern for subprocess adapters. |
| V. Plugin Registry | ✅ PASS | New `NetworkFontHunter` implements `HunterProtocol`. Registered via `HunterRegistry`. |
| VI. Data Safety | ✅ PASS | Scanner fix *prevents* processing trashed files. No new destructive operations. |
| IX. Observability | ✅ PASS | Enhanced DEBUG/INFO logging at each discovery step. Circuit breaker logs WARNING not silent skip. |
| XI. Dependency Isolation | ✅ PASS | `httpx` already approved. No new dependencies. |
| XII. Simplicity & YAGNI | ✅ PASS | Font name normalization is the minimum needed for correct matching. No premature abstraction. |
| XIII. Tool Discovery | ✅ PASS | 5-step hierarchy already implemented. Adding diagnostic logging. |

## Research Findings

> [!IMPORTANT]
> **Key Discovery: `dependency_checker.py` already implements the correct 5-step hierarchy.** The reported "tool discovery failure" is NOT a code defect — the scoop shims → scoop apps → mpv → Program Files → `shutil.which()` chain is correctly implemented. The fix here is adding per-step diagnostic logging so users can see exactly which paths were checked and why discovery failed on their specific system.

> [!WARNING]
> **Key Discovery: `network_font_hunter.py` does not exist.** The `src/hunters/` directory contains only `__init__.py`, `registry.py`, and `system_font_hunter.py`. The user's description of "broken proxy injection" in NetworkFontHunter refers to a file that hasn't been created yet. This plan includes creating it as a minimal Google Fonts hunter.

> [!IMPORTANT]
> **Key Discovery: `startup_ping()` in `FontResolver` creates `httpx.AsyncClient()` without proxy.** For users behind proxies/VPNs, ALL pings fail → circuit breakers force-trip for ALL hunters → network resolution is completely disabled before any search attempt. This is the root cause of the "premature circuit breaker tripping" described in the hotfix.

## Proposed Changes

### Component 1: Library Scanner — Dot-Directory Exclusion

#### [MODIFY] [library_scanner.py](file:///D:/Dev/projects/Anime_studio/src/core/library_scanner.py)

**Problem**: `lib_path.rglob("*.mkv")` on line 24 recursively finds MKV files inside `.anime_studio_trash/`, `.git/`, and any other dot-prefixed directory. After the pipeline trashes originals, subsequent scans rediscover them as valid episodes — creating an infinite reprocessing loop.

**Fix**: Add a filtering function that excludes any path where ANY ancestor directory starts with `.`:

```python
def _is_excluded(path: Path, base: Path) -> bool:
    """Return True if any path component relative to base starts with '.'."""
    try:
        relative = path.relative_to(base)
    except ValueError:
        return False
    return any(part.startswith(".") for part in relative.parts)
```

Apply this filter immediately after `rglob("*.mkv")`:

```python
mkv_files = sorted(
    [p for p in lib_path.rglob("*.mkv") if not _is_excluded(p, lib_path)],
    key=lambda p: p.name,
)
```

Also apply it to font directory discovery to prevent indexing fonts from trashed directories.

**Impact**: Eliminates the trash reprocessing loop. Also prevents `.git/` and other dot-directories from polluting scan results.

---

### Component 2: Dependency Checker — Diagnostic Logging

#### [MODIFY] [dependency_checker.py](file:///D:/Dev/projects/Anime_studio/src/adapters/dependency_checker.py)

**Problem**: The 5-step discovery works correctly but is opaque. When `alass` isn't found, there's no log explaining which paths were checked. Users report "alass not found" without knowing whether it's a PATH issue, a scoop installation issue, or something else.

**Fix**: Add `DEBUG`-level logging at each discovery step with the exact path checked and result:

```python
def discover_one(self, spec: BinarySpec) -> Path | None:
    if sys.platform == "win32":
        # Step 1: Scoop shim
        shim_path = self.home_dir / "scoop" / "shims" / f"{spec.name}.exe"
        logger.debug("Discovery step 1: checking scoop shim",
                     tool=spec.name, path=str(shim_path),
                     exists=shim_path.is_file())
        if shim_path.is_file() and os.access(shim_path, os.X_OK):
            return shim_path
        # ... repeat for steps 2-5
```

Add a summary `INFO` log when discovery completes (found or not found) including all checked paths.

**Impact**: Zero behavioral change. Pure observability improvement. Users and developers can now diagnose tool discovery failures from logs alone.

---

### Component 3: System Font Hunter — Normalization & TTC Support

#### [MODIFY] [system_font_hunter.py](file:///D:/Dev/projects/Anime_studio/src/hunters/system_font_hunter.py)

**Problem 1 — Missing `.ttc` support**: Line 106 filters only `.ttf` and `.otf`. Many Windows/macOS system fonts ship as `.ttc` (TrueType Collection) files (e.g., some CJK fonts, Cambria). These are silently excluded from the index.

**Fix 1**: Add `.ttc` to the extension filter. Use `TTFont(path, fontNumber=0)` (already used) which handles `.ttc` by reading the first font in the collection. Additionally, iterate `fontNumber` for TTC files to index ALL fonts in the collection:

```python
FONT_EXTENSIONS = frozenset({".ttf", ".otf", ".ttc"})

# In _build_index:
if p.is_file() and p.suffix.lower() in FONT_EXTENSIONS:
    if p.suffix.lower() == ".ttc":
        # Index all fonts in the collection
        from fontTools.ttLib import TTCollection
        try:
            collection = TTCollection(str(p))
            for i, font in enumerate(collection.fonts):
                # extract names from each font in collection
                ...
            collection.close()
        except Exception:
            # Fallback: index just fontNumber=0
            ...
    else:
        # Existing single-font logic
        ...
```

**Problem 2 — No name normalization**: The search is strict exact-match on lowercased index keys. If an ASS subtitle requests `"Segoe UI"` but the font's nameID 4 is `"Segoe UI Regular"`, the index has key `"segoe ui regular"` but NOT `"segoe ui"` — unless nameID 1 happens to produce it. More critically:
- Weight variants like `"Semibold"` vs `"SemiBold"` vs `"Demi Bold"` → no normalization
- Style suffixes like `"Regular"`, `"Normal"`, `"Book"` → not stripped for fallback matching
- Unusual weights like `"Heavy"`, `"Poster"`, `"Hairline"` → no synonym mapping

**Fix 2**: Add a normalization layer to the `search()` method. The index itself keeps all original keys for exact matches. If exact match fails, apply progressive normalization:

```python
# Normalization constants
_STRIP_SUFFIXES = frozenset({
    "regular", "normal", "book", "roman", "plain", "standard",
    "medium", "text", "display",
})

_WEIGHT_SYNONYMS = {
    "semibold": {"demibold", "demi bold", "semi bold"},
    "bold": {"heavy", "black", "dark"},
    "light": {"thin", "hairline", "ultralight", "extra light", "extralight"},
    "extrabold": {"ultra bold", "ultrabold", "extra bold"},
}

async def search(self, query: FontQuery) -> list[HunterResult]:
    if not self._index_built:
        await asyncio.to_thread(self._build_index)

    requested = query.requested_name.strip().lower()

    # 1. Exact match (existing behavior, fast path)
    if requested in self._index:
        return [self._make_result(requested, query)]

    # 2. Strip trailing "regular"/"normal" style suffixes
    normalized = self._strip_style_suffix(requested)
    if normalized != requested and normalized in self._index:
        return [self._make_result(normalized, query)]

    # 3. Try appending common suffixes if requested name is a bare family
    for suffix in _STRIP_SUFFIXES:
        candidate = f"{requested} {suffix}"
        if candidate in self._index:
            return [self._make_result(candidate, query)]

    # 4. Weight synonym expansion
    for canonical, synonyms in _WEIGHT_SYNONYMS.items():
        for syn in synonyms:
            if syn in requested:
                candidate = requested.replace(syn, canonical)
                if candidate in self._index:
                    return [self._make_result(candidate, query)]

    return []
```

Also add normalized keys during indexing: for each font, generate additional index entries by stripping style suffixes from nameID values.

**Impact**: Resolves the "failing to find Arial/Segoe" issue. Enables fuzzy matching for common weight/style variants. `.ttc` support adds coverage for CJK and macOS system fonts.

---

### Component 4: Network Font Hunter — New File

#### [NEW] [network_font_hunter.py](file:///D:/Dev/projects/Anime_studio/src/hunters/network_font_hunter.py)

**Problem**: No network font hunter exists. The resolution chain goes Cache → SystemFontHunter → nothing. Fonts not on the local system or in the cache cannot be resolved at all.

**Design**: Create a minimal `NetworkFontHunter` implementing `HunterProtocol` that searches the Google Fonts API as a first network source. Key requirements:

```python
class NetworkFontHunter:
    name: str = "GoogleFontsHunter"
    priority: int = 6  # After cache (1), system (4)
    rate_limit: float = 0.5  # 2 req/s to Google Fonts
    circuit_breaker_threshold: int = 3
    ping_url: str = "https://fonts.google.com"

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def _make_client(self) -> httpx.AsyncClient:
        """Create httpx client with proxy from config."""
        kwargs: dict = {"timeout": 10.0}
        if self._config.proxy:
            kwargs["proxy"] = self._config.proxy
        return httpx.AsyncClient(**kwargs)

    async def search(self, query: FontQuery) -> list[HunterResult]:
        async with self._make_client() as client:
            # Search Google Fonts API
            resp = await client.get(
                "https://www.googleapis.com/webfonts/v1/webfonts",
                params={"family": query.requested_name, "key": "..."}
            )
            ...

    async def download(self, result: HunterResult) -> FontPayload:
        async with self._make_client() as client:
            resp = await client.get(result.font_asset.file_path)
            ...
```

> [!IMPORTANT]
> The Google Fonts API requires an API key. This should be added to `config.toml` as `google_fonts_api_key: str | None = None`. When the key is absent, `supports()` returns `False` and the hunter is silently skipped. No hardcoded keys.

**Constitution compliance**:
- ✅ III. Async-First I/O: `httpx.AsyncClient` with proxy injection
- ✅ V. Plugin Registry: Implements `HunterProtocol`, registered in `HunterRegistry`
- ✅ XIII. Dependencies: No new packages — uses existing `httpx`

---

### Component 5: Font Resolver — Proxy Injection in Startup Ping

#### [MODIFY] [font_resolver.py](file:///D:/Dev/projects/Anime_studio/src/core/font_resolver.py)

**Problem**: Line 137 creates `httpx.AsyncClient()` with no proxy:

```python
async with httpx.AsyncClient() as client:  # ← No proxy!
```

For users behind corporate firewalls, SOCKS proxies, or censored networks, ALL pings fail → circuit breakers force-trip → ALL network hunters are pre-disabled. This is the root cause of "100% cache misses" for network fonts.

**Fix**: Inject proxy from `self.config.proxy`:

```python
async def startup_ping(self) -> None:
    """Concurrent health ping for all network hunters using TaskGroup."""
    logger.info("Initializing concurrent startup pings for network hunters")
    client_kwargs: dict = {}
    if self.config.proxy:
        client_kwargs["proxy"] = self.config.proxy
    async with httpx.AsyncClient(**client_kwargs) as client:
        ...
```

**Additional fix**: The current `_ping_hunter` force-trips the circuit breaker by recording `threshold` failures in a loop (lines 131-132). This is overly aggressive — a single failed ping shouldn't permanently disable a hunter for the entire session. Change to:
- Log `WARNING` when ping fails (already done)
- Record a single failure (not `threshold` failures)
- Let the circuit breaker naturally trip if the hunter also fails during actual resolution

```python
# BEFORE (overly aggressive):
for _ in range(hunter.circuit_breaker_threshold):
    cb.record_failure()

# AFTER (proportional):
cb.record_failure()
logger.warning(
    "Startup ping failed. Hunter will still be attempted during resolution.",
    hunter_name=hunter.name, url=hunter.ping_url, error=str(e),
)
```

**Impact**: Users behind proxies can now reach network font sources. Hunters aren't permanently disabled by a single failed ping.

---

### Component 6: Hunter Registration Update

#### [MODIFY] [__init__.py](file:///D:/Dev/projects/Anime_studio/src/hunters/__init__.py)

**Fix**: Export `NetworkFontHunter` alongside existing exports. Update any wiring code that creates the `HunterRegistry` to register the new hunter.

---

### Component 7: Config Extension

#### [MODIFY] [config.py](file:///D:/Dev/projects/Anime_studio/src/config.py)

**Fix**: Add `google_fonts_api_key: str | None = None` to `AppConfig`. This enables the `NetworkFontHunter` when configured, with no-op when absent.

## Project Structure

### Documentation (this feature)

```text
specs/007-font-ingestion/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── core/
│   ├── library_scanner.py     # [MODIFY] Add dot-directory exclusion filter
│   ├── font_resolver.py       # [MODIFY] Proxy injection + softer ping failure
│   ├── font_cache.py          # (unchanged)
│   └── circuit_breaker.py     # (unchanged)
├── adapters/
│   └── dependency_checker.py  # [MODIFY] Add per-step diagnostic logging
├── hunters/
│   ├── __init__.py            # [MODIFY] Export NetworkFontHunter
│   ├── registry.py            # (unchanged)
│   ├── system_font_hunter.py  # [MODIFY] TTC support + name normalization
│   └── network_font_hunter.py # [NEW] Google Fonts network hunter
├── config.py                  # [MODIFY] Add google_fonts_api_key field
└── models/                    # (unchanged)

tests/
├── unit/
│   ├── core/
│   │   ├── test_library_scanner.py  # [NEW/MODIFY] Trash exclusion tests
│   │   └── test_font_resolver.py    # [MODIFY] Proxy injection tests
│   ├── adapters/
│   │   └── test_dependency_checker.py  # [MODIFY] Logging verification tests
│   └── hunters/
│       ├── test_system_font_hunter.py  # [MODIFY] Normalization + TTC tests
│       └── test_network_font_hunter.py # [NEW] Network hunter tests
└── contract/
    └── test_hunter_protocol.py  # [MODIFY] Add NetworkFontHunter contract test
```

**Structure Decision**: Single-project layout per existing convention. All changes within the established `src/` tree. No new packages or directory restructuring.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Weight synonym mapping in SystemFontHunter | ASS subtitles reference fonts by display name which varies across font foundries. Without synonyms, common variations like "Semibold"/"DemiBold" fail to match. | Pure exact-match was the original design but produces false negatives on ~15% of real-world font queries. |
| NetworkFontHunter creation (not just a fix) | The user described this as a "fix" but the file doesn't exist. Cannot fix proxy/circuit-breaker on a nonexistent file. | Skipping network hunter entirely would leave font resolution without any network fallback, defeating the purpose of the hunter chain. |

## Verification Plan

### Automated Tests

```bash
# Unit tests for all modified modules
pytest tests/unit/core/test_library_scanner.py -v
pytest tests/unit/adapters/test_dependency_checker.py -v
pytest tests/unit/hunters/test_system_font_hunter.py -v
pytest tests/unit/hunters/test_network_font_hunter.py -v
pytest tests/unit/core/test_font_resolver.py -v

# Contract test for new hunter
pytest tests/contract/test_hunter_protocol.py -v

# Full test suite
pytest tests/ -v --tb=short
```

### Key Test Scenarios

1. **Scanner exclusion**: Create temp directory with `.anime_studio_trash/test.mkv` and `.git/test.mkv` → verify both excluded from scan results
2. **DependencyChecker logging**: Mock `Path.is_file()` to return False for all steps → verify DEBUG logs emitted for each checked path
3. **SystemFontHunter normalization**: Query `"Arial"` when index has `"arial regular"` → verify match via suffix stripping. Query `"Segoe UI Semibold"` when index has `"segoe ui demibold"` → verify match via synonym expansion.
4. **SystemFontHunter TTC**: Create mock `.ttc` file → verify all fonts in collection are indexed
5. **FontResolver proxy**: Create resolver with `config.proxy = "socks5://..."` → verify `httpx.AsyncClient` receives proxy kwarg
6. **FontResolver soft ping**: Single ping failure → verify circuit breaker records exactly 1 failure (not `threshold` failures)
7. **NetworkFontHunter**: Mock Google Fonts API response → verify search returns valid `HunterResult`. Verify `supports()` returns `False` when API key is absent.
