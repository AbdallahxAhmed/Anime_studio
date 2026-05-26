# Implementation Plan: Domain Models Layer

**Branch**: `001-domain-models` | **Date**: 2026-05-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-domain-models/spec.md`

## Summary

Build 11 pure Pydantic v2 domain models for Anime Studio v3 — the foundational data structures for font acquisition, subtitle processing, muxing, tool execution, and pipeline reporting. Zero I/O, zero cross-layer imports, frozen immutability, cross-platform Path serialization.

## Technical Context

**Language/Version**: Python 3.11+ (constitution §XI — `match`, `StrEnum`, `TaskGroup`)

**Primary Dependencies**: Pydantic v2 (`>=2.11.0`) — only runtime dependency for models layer

**Storage**: N/A — pure data models, no persistence (font_cache/font_library.toml handled by adapters)

**Testing**: pytest + pytest-asyncio (constitution §X). Models are sync — `pytest-asyncio` not needed for this feature but installed project-wide.

**Target Platform**: Windows-first, cross-platform (constitution §II)

**Project Type**: Library sub-package of CLI/TUI application

**Performance Goals**: N/A — model construction and validation are sub-millisecond operations

**Constraints**: Zero imports from `core/`, `adapters/`, `hunters/`, `tui/` (FR-015). All fields explicitly typed, no `Any` (FR-014).

**Scale/Scope**: 11 models across 6 files + 1 type alias file + `__init__.py` re-export

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Hexagonal Architecture** | ✅ PASS | Models in `src/models/` — no I/O, no cross-layer imports |
| **II. Cross-Platform** | ✅ PASS | `pathlib.Path` everywhere, POSIX serialization via `PosixPath` alias |
| **III. Async-First I/O** | ✅ N/A | No I/O in models layer |
| **IV. Structured Errors** | ✅ PASS | `ToolResult` model defined per constitution mandate |
| **V. Plugin Registry** | ✅ N/A | Registry implementation is separate feature; `HunterResult` model supports it |
| **VI. Data Safety** | ✅ N/A | No file operations in models |
| **VII. Subprocess Lifecycle** | ✅ N/A | `ToolResult` captures subprocess output; execution is adapters concern |
| **VIII. Encoding Guarantees** | ✅ PASS | `SubtitleFile.encoding_detected` / `encoding_source` fields support pipeline |
| **IX. Observability** | ✅ N/A | Logging is infrastructure concern |
| **X-bis. Pipeline Report** | ✅ PASS | `EpisodeReport`, `PipelineReport`, `EpisodeStatus` models defined |
| **X. Test-First** | ✅ PASS | Unit tests planned for all 11 models |
| **XI. Dependency Isolation** | ✅ PASS | Only `pydantic` imported (approved dependency) |
| **XII. Simplicity/YAGNI** | ✅ PASS | Flat module structure, 1-3 models per file, no premature abstractions |
| **XIII. Distribution** | ✅ N/A | No binary resolution in models layer |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-domain-models/
├── plan.md              # This file
├── research.md          # Phase 0 output — Pydantic v2 patterns
├── data-model.md        # Phase 1 output — entity definitions
├── quickstart.md        # Phase 1 output — usage examples
└── tasks.md             # Phase 2 output (via /speckit-tasks)
```

### Source Code (repository root)

```text
src/
└── models/
    ├── __init__.py      # Re-exports all public models
    ├── _types.py        # PosixPath type alias
    ├── font.py          # FontQuery, FontAsset, HunterResult
    ├── subtitle.py      # SubtitleFile, SyncResult
    ├── mux.py           # MuxJob, MuxResult
    ├── tool_result.py   # ToolResult
    └── report.py        # EpisodeStatus, EpisodeReport, PipelineReport

tests/
└── unit/
    └── models/
        ├── __init__.py
        ├── test_font.py
        ├── test_subtitle.py
        ├── test_mux.py
        ├── test_tool_result.py
        └── test_report.py
```

**Structure Decision**: Single project, flat models package. Each file groups 1-3 related models by domain boundary (font, subtitle, mux, tool, report). Shared type alias in `_types.py`. Constitution file organization followed exactly.

## Key Design Decisions

| Decision | Rationale | Research Ref |
|----------|-----------|--------------|
| `PosixPath` type alias with `PlainSerializer` | Cross-platform JSON portability, DRY across 6+ models | R-002 |
| `StrEnum` for `EpisodeStatus` | Python 3.11+ native, JSON-serializable without custom logic | R-003 |
| `dict[int, str]` for `nameids` | Maps OpenType name IDs directly, Pydantic handles int↔str key coercion | R-006 |
| `Field(ge=0, le=6)` for `layer_found` | Declarative constraint, clear validation errors | R-005 |
| 6 files not 1 or 11 | Balance between monolith and micro-files (constitution §XII) | R-004 |

## Complexity Tracking

> No violations — table empty.
