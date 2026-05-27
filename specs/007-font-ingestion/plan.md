# Implementation Plan: Font Ingestion System

**Branch**: `008-font-ingestion` | **Date**: 2026-05-27 | **Spec**: [spec.md](file:///d:/Dev/projects/Anime_studio/specs/007-font-ingestion/spec.md)

**Input**: Feature specification from `/specs/007-font-ingestion/spec.md`

## Summary

Add a multi-trigger font ingestion pipeline to Anime Studio v3. Three acquisition paths — system font resolution via `HunterProtocol`, auto-discovery from anime library `Fonts/` directories, and user-initiated import (button + drag-drop) — all converge on a single `FontIngestionService` in the core layer. System fonts are resolved in-place (`is_cacheable=False`) without copying. All other ingested fonts are deduped by `fonttools` nameID and stored atomically via `FontCache`. Feedback flows through `structlog` → `SignalBridge` → `ActivityFeedWidget`. An application-scoped `asyncio.Semaphore` bounds all concurrent disk I/O.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: PySide6, qasync, fonttools, structlog, pydantic

**Storage**: `font_library.toml` (TOML cache index), `.anime_studio/font_cache/` (font binaries)

**Testing**: pytest + pytest-asyncio

**Target Platform**: Windows (primary), Linux/macOS (cross-platform)

**Project Type**: Desktop application (GUI + CLI pipeline)

**Performance Goals**: <2s per system font lookup, <30s for 100-font bulk import, <500ms feedback latency

**Constraints**: Single asyncio event loop (qasync), no direct I/O from GUI layer, no Qt imports in core/hunters layers

**Scale/Scope**: ~500 system fonts indexed, 10-100 fonts per anime library, 1-500 fonts per manual import

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Hexagonal Architecture | ✅ PASS | `SystemFontHunter` in `src/hunters/`, `FontIngestionService` in `src/core/`, UI triggers in `src/gui/`. No cross-layer imports. |
| II. Cross-Platform | ✅ PASS | System font dirs via `sys.platform` + `pathlib.Path`. No hardcoded `.exe`. No Windows-only APIs. |
| III. Async-First I/O | ✅ PASS | All file reads via `asyncio.to_thread()`. Shared `asyncio.Semaphore` for disk I/O. No `shutil.copy2()` on main thread. |
| IV. Structured Error Handling | ✅ PASS | `FontIngestionResult` aggregates failures. Individual corrupt fonts logged at WARNING. No raw tracebacks. |
| V. Plugin Registry | ✅ PASS | `SystemFontHunter` registered via `HunterRegistry.register()`. Follows `HunterProtocol`. Open/Closed Principle maintained. |
| VI. Data Safety | ✅ PASS | `FontCache.store()` uses atomic writes (temp → replace). No original files modified. |
| VII. Subprocess Lifecycle | ✅ N/A | No subprocess calls in font ingestion. |
| VIII. Encoding | ✅ N/A | Binary font files, no encoding conversion needed. |
| IX. Observability | ✅ PASS | Ingestion results emitted via `structlog` with typed fields. Activity feed shows curated messages. |
| X-bis. Reports | ✅ N/A | Font ingestion doesn't produce pipeline reports. |
| X. Testing | ✅ PASS | Unit tests for all new components. Contract test for SystemFontHunter. Architecture boundary test updated. |
| XI. Dependencies | ✅ PASS | `fonttools` already approved. No new dependencies. |
| XII. Simplicity | ✅ PASS | One new service, one new hunter, one new model. No premature abstractions. |
| XIII. Distribution | ✅ N/A | No changes to distribution/launchers. |

**Forbidden Patterns Check**:
- No `flet`/`textual` imports ✅
- No `print()` for user output ✅
- No blocking subprocess calls ✅
- No `os.path.join()` ✅
- No hardcoded proxy URLs ✅
- No global mutable state ✅ (semaphore is injected, not global)

## Project Structure

### Documentation (this feature)

```text
specs/007-font-ingestion/
├── plan.md              # This file
├── research.md          # Phase 0 output (7 decisions)
├── data-model.md        # Phase 1 output (entities + relationships)
├── quickstart.md        # Phase 1 output (11 smoke tests)
├── contracts/           # Phase 1 output
│   └── font-ingestion-contracts.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── models/
│   ├── font.py              # MODIFY: add is_cacheable field to FontAsset
│   ├── pipeline.py          # MODIFY: add LibraryScanOutput wrapper model
│   └── ingestion.py         # NEW: FontIngestionResult value object
├── core/
│   ├── font_ingestion.py    # NEW: FontIngestionService (async, stateless)
│   ├── font_resolver.py     # MODIFY: skip download/cache when is_cacheable=False
│   ├── library_scanner.py   # MODIFY: detect Fonts/ dirs during scan, return LibraryScanOutput
│   └── pipeline_runner.py   # MODIFY: pre-pipeline ingestion step, injected semaphore
├── hunters/
│   └── system_font_hunter.py # NEW: SystemFontHunter (HunterProtocol, cross-platform)
└── gui/
    ├── main_window.py       # MODIFY: Import button, drag-drop, FontIngestionService wiring
    └── bootstrap.py         # MODIFY: DI for FontIngestionService, shared semaphore

tests/
├── unit/
│   ├── core/
│   │   ├── test_font_ingestion.py    # NEW: FontIngestionService tests
│   │   ├── test_font_resolver.py     # MODIFY: add is_cacheable short-circuit tests
│   │   ├── test_library_scanner.py   # MODIFY: add font dir detection tests
│   │   └── test_pipeline_runner.py   # MODIFY: add pre-pipeline ingestion tests
│   ├── hunters/
│   │   └── test_system_font_hunter.py # NEW: SystemFontHunter unit tests
│   ├── models/
│   │   ├── test_font.py              # MODIFY: add is_cacheable field tests
│   │   └── test_ingestion.py         # NEW: FontIngestionResult tests
│   └── gui/
│       └── test_main_window.py       # MODIFY: add import button + drag-drop tests
├── contract/
│   └── test_hunter_protocol.py       # MODIFY: add SystemFontHunter conformance
└── fixtures/
    └── fonts/                        # NEW: sample .ttf files for testing
```

**Structure Decision**: Single project structure per constitution. New files follow existing convention — one module per concern, flat where possible. `SystemFontHunter` lives in `src/hunters/` (not `src/hunters/sources/` — that directory doesn't exist yet, and a single file doesn't warrant a package). `FontIngestionService` in `src/core/` as a peer to `font_resolver.py`.

## Research Decisions

Detailed analysis in [research.md](file:///d:/Dev/projects/Anime_studio/specs/007-font-ingestion/research.md). Summary:

| # | Decision | Chosen | Key Rationale |
|---|----------|--------|---------------|
| 1 | System font enumeration | `sys.platform` + hardcoded OS dirs | Cross-platform, no Qt imports, no new deps |
| 2 | nameID matching | fonttools nameID 1, 4, 6, 16 | ASS refs by display name; filename matching unreliable |
| 3 | Async ingestion | `asyncio.to_thread` + `FontCache.store()` | Reuses atomic write safety, semaphore-gated |
| 4 | Scan output | New `LibraryScanOutput` wrapper | Separates per-episode and per-library data cleanly |
| 5 | FontResolver is_cacheable | 3-line short-circuit in resolve() | Minimal change, backward compatible |
| 6 | PySide6 drag-drop | `setAcceptDrops` + event overrides | Standard Qt pattern, full-window target |
| 7 | Shared semaphore | App-scoped singleton in bootstrap | Constitution mandate, bounds total disk I/O |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| PipelineRunner constructor change (add `disk_semaphore`) | Constitution mandates app-scoped singleton semaphore | Per-run semaphore creation violates Constitution Principle III |
| `scan_library()` return type change (`list` → `LibraryScanOutput`) | Font directories are per-library, not per-episode | Adding to each `LibraryScanResult` duplicates data wastefully |
