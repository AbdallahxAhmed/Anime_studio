# Research: Hotfix — Core Stability & Hunter Resolution (v1.7.0)

**Generated**: 2026-05-27 | **Status**: Complete

## Research Task 1: Scanner Trash Exclusion

**Decision**: Filter all dot-prefixed directories from `rglob()` results via a `_is_excluded()` helper.

**Rationale**: The scanner at `src/core/library_scanner.py` uses `lib_path.rglob("*.mkv")` with zero path filtering. Both `MuxJob.plan_trash_disposal()` and `SubtitleFile.plan_trash_disposal()` create trash paths under `.anime_studio_trash/` as siblings of episode directories. This means trashed MKV files are re-discovered as valid episodes on subsequent scans.

**Alternatives Considered**:
- **Hardcode `.anime_studio_trash` exclusion only**: Rejected — too narrow. `.git/`, `.vscode/`, and any future dot-directories would still pollute results. The Unix convention of hiding dot-prefixed directories is universal and safe.
- **Use `os.walk()` with `topdown=True` and prune dirs**: Considered — would be more efficient (avoids descending into excluded directories) but requires rewriting the entire scan loop. `rglob` + post-filter is simpler and the performance difference is negligible for typical anime library sizes (~1000 files).
- **Add an explicit exclusion list to config**: Over-engineering for a hotfix. Can be added later if needed.

**Implementation Note**: The filter must check ALL path components relative to the library root, not just the immediate parent. A deeply nested `.anime_studio_trash/Season 1/foo.mkv` must also be excluded.

---

## Research Task 2: Dependency Checker Discovery Hierarchy

**Decision**: No functional changes needed. Add per-step diagnostic logging only.

**Rationale**: The existing `discover_one()` method in `src/adapters/dependency_checker.py` correctly implements all 5 steps from Constitution Section XIII:
1. `~/scoop/shims/<tool>.exe` ✓
2. `~/scoop/apps/<tool>/current/**/<tool>.exe` ✓
3. `C:\Program Files\mpv\<tool>.exe` ✓
4. `C:\Program Files\<win_folder_name>\**\<tool>.exe` ✓
5. `shutil.which(<tool>)` ✓

The original bug report stating this "violates the 5-step discovery rule" is incorrect — the code is already compliant. The real issue is that when discovery fails, there is zero diagnostic output explaining which paths were checked.

**Alternatives Considered**:
- **Rewrite discovery logic**: Rejected — the logic is already correct. Rewriting would risk introducing regressions.
- **Add a `--diagnose-tools` CLI flag**: Over-scoped for a hotfix. DEBUG logging is sufficient.

---

## Research Task 3: System Font Hunter Name Extraction

**Decision**: Add `.ttc` support + multi-tier normalization in `search()`.

**Rationale**: The `_extract_font_names()` function correctly extracts nameIDs 1, 4, 6, 16 from both Windows (platformID=3) and Mac (platformID=1) records. However:

1. **Missing `.ttc`**: Line 106 filters only `.ttf`/`.otf`. TrueType Collections (`.ttc`) are common on Windows (CJK fonts) and macOS (many system fonts). `fonttools.TTFont` can open `.ttc` files via `fontNumber=0`, but only indexes the first font. Full coverage requires `TTCollection` iteration.

2. **No normalization**: The `search()` method does `requested in self._index` — a strict exact-match on lowercased strings. This fails when:
   - ASS requests `"Arial"` but index only has `"arial regular"` (nameID 4 included the style)
   - ASS requests `"Segoe UI Semibold"` but font uses `"Segoe UI SemiBold"` (casing) or `"Segoe UI Demi Bold"` (synonym)
   - Font uses unusual weight names like `"Heavy"`, `"Poster"`, `"Hairline"`

**Normalization Strategy** (progressive, from cheapest to most expensive):
1. Exact match (existing fast path)
2. Strip trailing style suffixes ("Regular", "Normal", "Book", "Roman", etc.)
3. Try appending common suffixes to bare family name
4. Weight synonym expansion (e.g., "Semibold" ↔ "Demi Bold")

**Alternatives Considered**:
- **Fuzzy matching (Levenshtein distance)**: Rejected — too risky for a hotfix. False positives (matching the wrong font) are worse than false negatives. Can be explored in a future iteration.
- **Pre-normalize all index keys during build**: Partially adopted — generate additional stripped keys during index build. But keep originals too for exact-match fast path.

---

## Research Task 4: Network Font Hunter Architecture

**Decision**: Create a new `NetworkFontHunter` implementing `HunterProtocol` with Google Fonts API as the initial source.

**Rationale**: `src/hunters/` contains only `registry.py` and `system_font_hunter.py`. No network-based font resolution exists. The resolution chain is Cache → SystemFontHunter → failure. Any font not installed locally and not in the cache is unresolvable.

**Design Decisions**:
- **Single file, single source (Google Fonts)**: Start minimal. Additional sources (DaFont, FontSquirrel) can be added as separate hunter implementations later.
- **API key gated**: `supports()` returns `False` when `google_fonts_api_key` is absent from config. Zero functionality when unconfigured — no crashes, no errors.
- **Client-per-request**: Create `httpx.AsyncClient` per operation via `_make_client()`. Avoids holding open connections and simplifies proxy injection. The rate limiter in `FontResolver` already throttles requests.
- **Priority 6**: After cache (implicit layer 1) and system fonts (priority 4). Before any future lower-priority hunters.

**Alternatives Considered**:
- **Scraping Google Fonts website**: Rejected — fragile, violates ToS, blocked by CDN. API is stable and free.
- **Bundling a font list**: Rejected — becomes stale. Live API query ensures up-to-date results.
- **Making network hunter mandatory**: Rejected — many users run offline or behind strict firewalls. Optional-by-API-key is the right default.

---

## Research Task 5: Startup Ping & Circuit Breaker Behavior

**Decision**: Inject `config.proxy` into `startup_ping()`'s `httpx.AsyncClient`. Reduce ping failure from force-trip to single failure record.

**Rationale**: `FontResolver.startup_ping()` at line 137 creates `httpx.AsyncClient()` with no arguments. For proxy users, ALL pings fail. The `_ping_hunter()` method then force-trips the circuit breaker by recording `threshold` failures in a loop (lines 131-132). This means a single failed ping permanently disables the hunter for the entire session (60s cooldown, but by then the pipeline is likely done).

**Circuit Breaker Analysis** (`src/core/circuit_breaker.py`):
- States: CLOSED → OPEN (after `threshold` consecutive failures) → HALF_OPEN (after `cooldown_s`) → CLOSED (on success) or OPEN (on failure)
- Default threshold: 3, default cooldown: 60s
- The force-trip loop (`for _ in range(threshold): cb.record_failure()`) immediately transitions to OPEN, skipping the natural escalation path

**Fix**: Record only 1 failure per failed ping. If the hunter also fails during actual resolution, the natural 3-failure threshold still trips the breaker. This gives the hunter a fair chance to work even if the ping URL was temporarily unreachable.

**Alternatives Considered**:
- **Remove startup pings entirely**: Rejected — they provide useful early warning about network issues. Just need to be less aggressive.
- **Add a "soft" circuit breaker state**: Over-engineering. Single failure record achieves the same effect within the existing state machine.
- **Make ping failure non-counting**: Rejected — pings DO provide signal about network health. One failure should count as one data point.

---

## Research Task 6: Font Cache Normalization Gap

**Decision**: Out of scope for this hotfix. Document as follow-up.

**Rationale**: `FontCache.lookup()` at line 111 does `if font_name not in fonts` — a strict exact-match on the raw font name string. This means the cache has the same normalization gap as the hunter. However, fixing the cache is a broader change that affects store/lookup/rebuild semantics and the TOML index format. The immediate hotfix should focus on the hunter layer where fonts are first resolved. Once the SystemFontHunter returns a properly matched `FontAsset`, the cache stores it under the correct name for future lookups.

**Follow-up**: Add normalization to `FontCache.lookup()` in a future iteration, potentially using the same `_strip_style_suffix()` and synonym logic.
