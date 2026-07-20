# Feature Specification: Complete Font Hunter Chain (Phase 6.6)

**Feature Branch**: `008-font-hunter-chain`

**Created**: 2026-06-06

**Status**: Draft

**Input**: User description: "Phase 6.5 diagnostic confirmed SystemFontHunter works. Root problem: only Layer 3 is registered. Layers 1,2,4,5 never run. Also: FuzzyMatch is architecturally wrong — the system must find the EXACT font, not a substitute. Spec the complete font hunter chain."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Full Layer Resolution Chain (Priority: P1)

A user points their anime library at the pipeline. The system resolves every font referenced in ASS subtitles by walking the complete 6-layer resolution chain: cache → MKV-embedded extraction → sibling `Fonts/` dirs → system fonts → known online repositories → search engine discovery. The output MKV contains all required fonts as attachments.

**Why this priority**: This is the entire purpose of the application. Without all layers working, the muxed MKV will not render Arabic subtitles correctly.

**Independent Test**: Run pipeline against an anime folder containing ASS subtitles referencing a mix of system fonts (Arial, Segoe UI), uncommon fansub fonts (Sakkal Majalla, GE SS Two), and popular free fonts (Lato, Open Sans). Verify `mkvinfo output.mkv` lists all fonts as attachments.

**Acceptance Scenarios**:

1. **Given** an anime folder with ASS referencing Arial and Segoe UI, **When** pipeline runs, **Then** SystemFontHunter (Layer 3) resolves both from `C:\Windows\Fonts` without network calls.
2. **Given** an anime folder with ASS referencing "Lato Bold", **When** pipeline runs and cache is empty, **Then** GoogleFontsHunter (Layer 4) downloads Lato Bold, verifies with fontTools, caches it, and attaches to MKV.
3. **Given** an anime folder with ASS referencing a rare Arabic font "GE SS Two", **When** no online repository has it, **Then** SearchEngineHunter (Layer 5) queries DuckDuckGo, finds a download page, downloads `.ttf`, verifies with fontTools, caches it, and attaches to MKV.
4. **Given** all 5 layers fail to find font "NonExistentFont2099", **When** resolution exhausts, **Then** system logs ERROR "Font 'NonExistentFont2099' not found on any known source. Mux will proceed without this font." No user prompt. No substitute font. Pipeline continues for remaining fonts.

---

### User Story 2 - FuzzyMatch Removal (Priority: P1)

The system never substitutes a different font for the requested one. If "Sakkal Majalla" is requested, the system finds exactly "Sakkal Majalla" or reports it as missing. A Levenshtein-distance fuzzy match cannot make aesthetic judgments about Arabic typography.

**Why this priority**: Fuzzy matching fundamentally violates the project's purpose. Arabic fansub fonts are chosen for specific aesthetic and legibility reasons. Substituting "Sakkal" with "Sagoe" (or any close-spelling font) ruins the typographic intent.

**Independent Test**: Request resolution of a font with a close-spelling match to an existing system font. Verify the system does NOT return the similar-name font and instead reports the exact font as missing.

**Acceptance Scenarios**:

1. **Given** FuzzyMatchHunter previously existed in Layer 5, **When** the system is updated, **Then** all references to FuzzyMatchHunter are removed from code, tests, and documentation.
2. **Given** a font query for "Segue UI" (misspelled), **When** resolution runs, **Then** system reports it as not found. It does NOT return "Segoe UI" as a substitute.

---

### User Story 3 - Known Font Repository Discovery (Priority: P1)

The system queries well-known free font repositories (Google Fonts, FontSquirrel, DaFont, FontSpace, Befonts, and Arabic font sites) before resorting to search engine crawling. Each repository is a separate hunter class with independent circuit breaker, rate limiting, and health tracking.

**Why this priority**: These repositories cover the vast majority of fonts used in anime fansubs. Google Fonts alone has 1,600+ families. DaFont and FontSpace cover decorative and display fonts common in title cards. Arabic font sites cover the community-specific fonts.

**Independent Test**: With cache empty and system fonts insufficient, run pipeline against ASS referencing "Open Sans". Verify GoogleFontsHunter resolves it without needing SearchEngineHunter.

**Acceptance Scenarios**:

1. **Given** font "Roboto" requested, **When** GoogleFontsHunter queries, **Then** it downloads the exact weight/style, verifies with fontTools, and returns a valid FontPayload.
2. **Given** font "Bleeding Cowboys" requested, **When** GoogleFontsHunter returns no result, **Then** DaFontHunter or FontSpaceHunter queries its index and resolves the font.
3. **Given** GoogleFontsHunter fails 3 consecutive times, **When** circuit breaker trips, **Then** GoogleFontsHunter is skipped for the remainder of the session. Other Layer 4 hunters continue operating independently.
4. **Given** an Arabic font "Amiri" is requested, **When** it exists on Google Fonts, **Then** GoogleFontsHunter resolves it. Arabic font sites are not queried.

---

### User Story 4 - Search Engine Last Resort (Priority: P2)

When all known repositories fail, the system performs a DuckDuckGo HTML search as a "nuclear option" before giving up. This catches obscure fonts from personal blogs, GitHub releases, and niche foundry sites.

**Why this priority**: Covers the long tail of fonts that don't appear in any curated repository. Important for completeness but most fonts will be caught by Layers 0–4.

**Independent Test**: With all Layer 4 hunters failing or returning no results, verify SearchEngineHunter queries DuckDuckGo, parses results, downloads and verifies a font file.

**Acceptance Scenarios**:

1. **Given** font "GE SS Two" not found in any repository, **When** SearchEngineHunter queries DuckDuckGo for "GE SS Two font free download ttf", **Then** it parses top 10 results, finds a direct `.ttf` download link, downloads it, verifies with fontTools, and caches it.
2. **Given** a DuckDuckGo result points to a blocked/spam domain, **When** SearchEngineHunter evaluates the URL, **Then** it skips the domain and tries the next result.
3. **Given** all 10 DuckDuckGo results contain no valid `.ttf`/`.otf` downloads, **When** SearchEngineHunter exhausts results, **Then** it returns empty results and the font is marked as genuinely missing.

---

### User Story 5 - Layers 1 and 2 Registration (Priority: P1)

The MKV-embedded font extractor (Layer 1) and sibling directory scanner (Layer 2) are registered in the hunter chain at bootstrap. Currently these layers exist as concepts in the architecture but have no hunter classes registered.

**Why this priority**: These are the fastest resolution paths after cache. MKV-embedded fonts are already inside the file being processed. Sibling `Fonts/` dirs are the standard fansub font distribution method.

**Independent Test**: Place a folder of anime episodes where one MKV already contains embedded fonts referenced by another episode's ASS. Verify MkvExtractHunter extracts and caches the font for the second episode.

**Acceptance Scenarios**:

1. **Given** an anime folder with a `Fonts/` subdirectory containing `CustomFont.ttf`, **When** pipeline runs and ASS references "CustomFont", **Then** SiblingFontHunter (Layer 2) finds it in the sibling directory and returns the font.
2. **Given** an MKV with embedded font attachments, **When** another episode in the same library needs one of those fonts, **Then** MkvExtractHunter (Layer 1) extracts and caches it.

---

### Edge Cases

- What happens when a font repository returns HTTP 429 (rate limited)? → Circuit breaker records failure; rate limit delay increases for that hunter.
- What happens when a downloaded file claims to be `.ttf` but is corrupt/invalid? → fontTools verification rejects it; hunter returns no result; next hunter in chain tries.
- What happens when the proxy setting is configured but the proxy is down? → httpx timeout fires; circuit breaker records failure; logs WARNING with proxy details.
- What happens when DuckDuckGo changes its HTML structure? → SearchEngineHunter parsing fails gracefully; returns empty results; font marked as missing.
- What happens when two Layer 4 hunters both have the same font? → First hunter in priority order wins; second hunter is never queried for that font.
- What happens when a `.ttc` (TrueType Collection) is downloaded from a repository? → fontTools TTCollection support extracts and indexes each face separately.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST register ALL hunter layers (0 through 5) at bootstrap in `bootstrap.py`. No layer may be silently omitted.
- **FR-002**: System MUST completely remove FuzzyMatchHunter from all source code, tests, documentation, and COMPACT_STATE.md references.
- **FR-003**: System MUST implement separate hunter classes for Google Fonts, FontSquirrel, DaFont, FontSpace, Befonts, and at least one Arabic font repository, each in `src/hunters/sources/`.
- **FR-004**: System MUST implement SearchEngineHunter (Layer 5) querying DuckDuckGo HTML search with the pattern `"{font_name} font free download ttf"`.
- **FR-005**: Every downloaded font file MUST be verified with fontTools before caching or returning. Invalid/corrupt files MUST be rejected silently.
- **FR-006**: Each hunter MUST implement the full `HunterProtocol` interface including `name`, `priority`, `rate_limit`, `circuit_breaker_threshold`, `ping_url`, `supports()`, `search()`, and `download()`.
- **FR-007**: Circuit breaker MUST trip after 3 consecutive failures per hunter per session. Tripped hunters MUST be skipped silently with a WARNING log.
- **FR-008**: All HTTP requests MUST use `httpx.AsyncClient` with proxy support from `config.toml`, explicit timeouts, and connection pooling.
- **FR-009**: Rate limiting between requests MUST use `asyncio.sleep()`, never `time.sleep()`.
- **FR-010**: Downloaded fonts with `is_cacheable=True` MUST be stored in `font_cache/` via `FontCache.store()`.
- **FR-011**: When ALL layers are exhausted for a font, system MUST log ERROR: "Font '{name}' not found on any known source. Mux will proceed without this font." System MUST NOT prompt the user. System MUST NOT substitute a different font.
- **FR-012**: MkvExtractHunter (Layer 1) MUST extract font attachments from existing MKV files in the library using `mkvextract`.
- **FR-013**: SiblingFontHunter (Layer 2) MUST scan `Fonts/` and `fonts/` directories adjacent to episode files.
- **FR-014**: SearchEngineHunter MUST filter results against a blocked domain list to exclude known spam/malware sites.
- **FR-015**: SearchEngineHunter MUST parse downloaded HTML pages to find direct `.ttf`/`.otf`/`.ttc` download links.
- **FR-016**: SearchEngineHunter MUST limit search to top 10 DuckDuckGo results per query.

### Key Entities

- **HunterProtocol**: Interface contract all hunters implement. Defines `search()`, `download()`, `supports()`, circuit breaker threshold, rate limit.
- **FontQuery**: Immutable query containing `requested_name`, `anime_title`, `episode_path`.
- **HunterResult**: Search result from a hunter, optionally containing resolved `FontAsset`.
- **FontPayload**: Raw font bytes with metadata, ready for cache storage.
- **FontAsset**: Resolved font with path, source, layer info, nameIDs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Pipeline resolves 95%+ of fonts referenced in ASS subtitles across a typical Arabic anime fansub library (20+ episodes, 10+ distinct fonts) without manual intervention.
- **SC-002**: System fonts (Arial, Segoe UI, Corbel) resolve in under 500ms each via SystemFontHunter (no network).
- **SC-003**: Popular free fonts (Roboto, Open Sans, Lato) resolve via Layer 4 network hunters within 10 seconds each including download and verification.
- **SC-004**: When a font genuinely does not exist anywhere, resolution completes within 30 seconds (all layers tried) and produces a clear error log — no hanging, no user prompt.
- **SC-005**: `mkvinfo` on output MKVs shows all resolved fonts listed as attachments.
- **SC-006**: Zero occurrences of fuzzy/approximate font matching in the codebase after this phase.

## Assumptions

- DuckDuckGo HTML search results can be parsed without requiring JavaScript rendering (static HTML scraping is sufficient for the `html.duckduckgo.com` endpoint).
- Google Fonts API is freely accessible without API keys for font file downloads (the `fonts.google.com` download URLs are public).
- FontSquirrel, DaFont, FontSpace, and Befonts have parseable HTML pages or APIs for font search and download.
- The user has internet access (possibly through a proxy configured in `config.toml`).
- Font repositories do not require authentication for free font downloads.
- All Layer 4 and Layer 5 hunters require internet access; they are no-ops when offline (circuit breaker trips on first timeout).
- Layer 1 (MkvExtractHunter) requires `mkvextract` binary to be available (already CRITICAL dependency).
- Layer 2 (SiblingFontHunter) operates entirely on the local filesystem with no network requirements.
