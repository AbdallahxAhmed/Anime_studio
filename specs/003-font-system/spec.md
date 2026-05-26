# Feature Specification: Font System

**Feature Branch**: `003-font-system`

**Created**: 2026-05-26

**Status**: Draft

**Input**: User description: "Phase 2 (Font System). Focus on FontCache, HunterRegistry, and SubtitleRepair using the 6-layer fallback strategy. Circuit Breaker as IN-MEMORY state machine within core layer, fast-fail lightweight ping on initial network requests to prevent startup delays. HunterProtocol strictly typed."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Font Cache Lookup and Population (Priority: P1)

When the pipeline encounters a subtitle file requesting specific fonts, the system resolves them from a persistent on-disk cache before attempting any network requests. The cache stores previously downloaded fonts indexed by font name, tracks source provenance, and includes a version stamp for invalidation. On cache hit, the font is returned instantly. On miss, the font is queued for hunter resolution.

**Why this priority**: The cache is the fastest resolution layer (Layer 1) and prevents redundant downloads for commonly-used fonts. Every other resolution strategy depends on the cache for write-back storage.

**Independent Test**: Can be fully tested by creating a pre-populated font cache directory, querying for known/unknown fonts, and verifying hit/miss behavior and TOML index integrity.

**Acceptance Scenarios**:

1. **Given** a font cache containing "Roboto-Regular.ttf" indexed in `font_library.toml`, **When** the system queries for font name "Roboto", **Then** it returns a `FontAsset` with `cache_hit=True`, `layer_found=1`, and the correct file path.
2. **Given** an empty font cache, **When** the system queries for "Roboto", **Then** it returns `None` and the query proceeds to the next resolution layer.
3. **Given** a `font_library.toml` with `cache_version = "2.0"` but the app expects `"3.0"`, **When** the cache is loaded, **Then** the stale index is deleted and the cache rebuilds by scanning `font_cache/` directory contents.
4. **Given** a hunter successfully downloads a new font, **When** the font is written to cache, **Then** `font_library.toml` is updated atomically with the new entry and `cache_version` preserved.

---

### User Story 2 - Hunter Registry with 6-Layer Fallback (Priority: P1)

When a font cannot be resolved from the cache, the system executes a multi-layer fallback strategy through a registry of font acquisition sources (hunters). Each hunter is tried in priority order. Layers:

1. **Layer 1 — Local Cache**: `font_cache/` directory lookup
2. **Layer 2 — MKV Extraction**: Extract font attachments from the episode MKV itself
3. **Layer 3 — Sibling Scan**: Scan sibling directories for font files
4. **Layer 4 — System Fonts**: Query OS-installed fonts via fontTools
5. **Layer 5 — Network Hunters**: Web-based font acquisition (Google Fonts, DaFont, etc.)
6. **Layer 6 — Fuzzy Match / Substitution**: Best-effort fuzzy name matching with user-approved substitution

The registry iterates through hunters, skipping those whose circuit breaker is open.

**Why this priority**: The fallback chain is the core font resolution algorithm. Without it, the pipeline cannot resolve fonts.

**Independent Test**: Can be tested by registering mock hunters with controlled success/failure patterns and verifying the registry tries them in priority order, skips circuit-broken hunters, and returns the first successful result.

**Acceptance Scenarios**:

1. **Given** a registry with hunters for Layers 1-6, **When** Layer 1 misses and Layer 2 succeeds, **Then** the system returns the Layer 2 result and does not invoke Layers 3-6.
2. **Given** a hunter for Layer 5 with an open circuit breaker, **When** resolution reaches Layer 5, **Then** the registry skips that hunter silently, logs a WARNING, and proceeds to Layer 6.
3. **Given** all hunters fail, **When** the full chain is exhausted, **Then** a `FontMatchError` is raised containing the audit trail of all attempted hunters and their failure reasons.
4. **Given** a new hunter is registered at runtime, **When** resolution runs, **Then** the new hunter is included at its declared priority position without code changes.

---

### User Story 3 - Circuit Breaker State Machine (Priority: P1)

The circuit breaker protects the system from repeated calls to failing font sources. It is implemented as an in-memory state machine within the core layer (not in adapters or hunters). States:

- **CLOSED** (normal): Requests flow through. Failure counter increments on each failure.
- **OPEN** (tripped): All requests fast-fail immediately. Entered when consecutive failures reach `circuit_breaker_threshold`.
- **HALF_OPEN** (probing): After a cooldown period, a single probe request is allowed. Success → CLOSED, failure → OPEN.

On application startup, a lightweight ping (HEAD request or connection-only probe) is sent to network hunters to pre-check availability. This ping MUST be non-blocking, fire-and-forget, and complete within 2 seconds. If the ping fails, the circuit opens immediately — preventing the pipeline from waiting on unreachable sources.

**Why this priority**: Without the circuit breaker, a single downed font source can block the entire pipeline with timeouts. The fast-fail ping prevents startup delays.

**Independent Test**: Can be tested by simulating hunter failures, verifying state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED), and confirming the startup ping opens circuits for unreachable sources.

**Acceptance Scenarios**:

1. **Given** a hunter with `circuit_breaker_threshold=3` in CLOSED state, **When** it fails 3 consecutive times, **Then** the circuit transitions to OPEN and subsequent requests fast-fail without invoking the hunter.
2. **Given** an OPEN circuit, **When** the cooldown period elapses, **Then** the circuit transitions to HALF_OPEN and allows exactly one probe request.
3. **Given** a HALF_OPEN circuit, **When** the probe request succeeds, **Then** the circuit transitions to CLOSED and resets the failure counter to 0.
4. **Given** a HALF_OPEN circuit, **When** the probe request fails, **Then** the circuit transitions back to OPEN and resets the cooldown timer.
5. **Given** application startup, **When** network hunters are registered, **Then** a lightweight ping is dispatched concurrently for each. Hunters that fail the ping start with an OPEN circuit. Ping completes within 2 seconds total.

---

### User Story 4 - Strictly Typed HunterProtocol (Priority: P2)

The `HunterProtocol` defines the contract that all font acquisition sources must implement. It is a `typing.Protocol` with `@runtime_checkable` decorator, enabling both static type checking and runtime `isinstance()` validation during registration. The protocol includes:

- `name: str` — unique identifier
- `priority: int` — resolution order (lower = tried first)
- `rate_limit: float` — max requests per second to this source
- `circuit_breaker_threshold: int` — consecutive failures before circuit opens (default: 3)
- `async def search(query: FontQuery) -> list[HunterResult]` — find matching fonts
- `async def download(result: HunterResult) -> FontPayload` — download a matched font
- `def supports(query: FontQuery) -> bool` — pre-filter for capability check

A `FontPayload` model carries the raw font bytes plus metadata for cache write-back.

**Why this priority**: The protocol must be defined before any hunter implementations can be built. It serves as the compile-time contract for the plugin system.

**Independent Test**: Can be tested by creating conforming and non-conforming classes, verifying `isinstance()` checks pass/fail appropriately, and running `mypy --strict` to confirm static type safety.

**Acceptance Scenarios**:

1. **Given** a class implementing all `HunterProtocol` methods with correct signatures, **When** `isinstance(hunter, HunterProtocol)` is checked, **Then** it returns `True`.
2. **Given** a class missing the `download` method, **When** `isinstance()` is checked, **Then** it returns `False`.
3. **Given** the protocol definition, **When** `mypy --strict` runs on a file importing it, **Then** zero type errors are reported.

---

### User Story 5 - Subtitle Font Extraction and Repair (Priority: P2)

When a subtitle file (ASS format) is loaded, the system extracts all font references from the `[V4+ Styles]` section, normalizes font names (stripping weight suffixes, handling aliases), and produces a deduplicated list of `FontQuery` objects for resolution. If the ASS file has structural issues (missing sections, malformed style lines), the system attempts repair before font extraction.

**Why this priority**: Font extraction bridges the subtitle model with the font resolution pipeline. Without it, the system cannot determine which fonts to find.

**Independent Test**: Can be tested by parsing sample ASS files (valid, corrupt, edge cases) and verifying the extracted font list matches expectations.

**Acceptance Scenarios**:

1. **Given** a valid ASS file with 5 styles using 3 unique fonts, **When** font extraction runs, **Then** it produces 3 deduplicated `FontQuery` objects.
2. **Given** a style line with `Fontname=Arial Bold`, **When** extraction normalizes it, **Then** the query `requested_name` is "Arial" (weight suffix stripped).
3. **Given** an ASS file with a missing `[V4+ Styles]` section, **When** repair runs, **Then** it raises `EncodingRepairError` with a descriptive message (section is unrecoverable).
4. **Given** an ASS file with a malformed style line (wrong field count), **When** repair runs, **Then** the malformed line is logged as WARNING and skipped, remaining lines are processed.

---

### Edge Cases

- What happens when the font cache directory does not exist at startup? → Created automatically.
- What happens when `font_library.toml` is corrupted (invalid TOML)? → Deleted and rebuilt from directory scan.
- What happens when two concurrent pipeline runs write to the same cache? → Atomic writes via temp file + rename prevent corruption. Last writer wins for index entries.
- What happens when a hunter returns a font file that fails fontTools validation? → Font is not cached, `HunterResult.success = False`, warning logged, next hunter tried.
- What happens when all network hunters time out during startup ping? → All network circuits open. Pipeline proceeds with local-only resolution (Layers 1-4). User warned via structured log.
- What happens when a font name contains non-ASCII characters (CJK, Arabic)? → Font name preserved as-is in queries. Matching is case-insensitive but encoding-preserving.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain a persistent font cache at `D:\Entertainment\.anime_studio\font_cache\` indexed by `font_library.toml` with `cache_version` validation.
- **FR-002**: System MUST implement a 6-layer font resolution fallback chain: Cache → MKV Extract → Sibling Scan → System Fonts → Network Hunters → Fuzzy Match.
- **FR-003**: System MUST implement a `HunterRegistry` supporting runtime registration, priority-ordered iteration, and graceful skip on individual hunter failure.
- **FR-004**: System MUST implement an in-memory circuit breaker state machine (CLOSED/OPEN/HALF_OPEN) within `src/core/` tracking per-hunter failure counts per session.
- **FR-005**: System MUST perform a lightweight non-blocking startup ping (≤2s total) on network hunters, opening circuits for unreachable sources before pipeline execution begins.
- **FR-006**: The `HunterProtocol` MUST be a `typing.Protocol` with `@runtime_checkable`, declaring: `name`, `priority`, `rate_limit`, `circuit_breaker_threshold`, `search()`, `download()`, `supports()`.
- **FR-007**: System MUST extract font references from ASS subtitle `[V4+ Styles]` sections, normalizing font names and deduplicating into `FontQuery` objects.
- **FR-008**: System MUST repair recoverable ASS structural issues (malformed style lines) before font extraction, logging warnings for skipped lines.
- **FR-009**: On circuit breaker state transition, system MUST log at appropriate level: INFO for CLOSED→OPEN, DEBUG for OPEN→HALF_OPEN, INFO for HALF_OPEN→CLOSED.
- **FR-010**: System MUST support rate limiting per hunter, enforcing `rate_limit` requests per second with async-compatible throttling.
- **FR-011**: Font cache writes MUST be atomic (temp file + rename). `font_library.toml` updates MUST preserve `cache_version`.
- **FR-012**: A `FontPayload` model MUST carry raw font bytes, font name metadata, and source provenance for cache write-back.

### Key Entities

- **FontCache**: Manages the `font_cache/` directory and `font_library.toml` index. Responsible for lookup, write-back, and version validation.
- **HunterRegistry**: Container for `HunterProtocol` implementations. Provides priority-ordered iteration with circuit breaker awareness.
- **CircuitBreaker**: In-memory state machine (CLOSED/OPEN/HALF_OPEN) tracking consecutive failures per hunter. Lives in `src/core/`.
- **HunterProtocol**: Strictly typed protocol defining the contract for font acquisition sources.
- **FontPayload**: Value object carrying downloaded font bytes + metadata.
- **SubtitleRepair**: Service that extracts font references from ASS files and repairs structural issues.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Font cache lookup returns results within 50ms for a cache of 500+ fonts.
- **SC-002**: The 6-layer fallback chain resolves 95% of fonts for typical anime episodes (10-15 unique fonts) without user intervention.
- **SC-003**: Startup ping completes within 2 seconds, regardless of how many network hunters are registered.
- **SC-004**: Circuit breaker correctly prevents calls to failing sources, reducing wasted network time by 90% when a source is down.
- **SC-005**: All `HunterProtocol` implementations pass `isinstance()` runtime checks and `mypy --strict` static analysis.
- **SC-006**: ASS font extraction correctly identifies all unique fonts from subtitle files, with 100% accuracy on well-formed files and graceful degradation on malformed files.
- **SC-007**: Font cache index survives version upgrades — stale caches are rebuilt, not corrupted.

## Assumptions

- The font cache directory (`D:\Entertainment\.anime_studio\font_cache\`) is writable by the application at runtime.
- `fontTools` is available as a Python dependency for font introspection and validation.
- Network hunters (Layer 5) are implemented as separate hunter modules in `src/hunters/sources/` — this spec defines only the protocol and registry, not individual hunter implementations.
- The circuit breaker cooldown period defaults to 60 seconds and is configurable via `config.toml`.
- ASS subtitle format follows the v4+ specification (v4 is not supported).
- The MKV extraction hunter (Layer 2) depends on the `mkvmerge`/`mkvextract` adapter from Phase 1 (002-core-adapters).
