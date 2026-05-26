# Implementation Plan: Pipeline Orchestration

**Branch**: `004-pipeline` | **Date**: 2026-05-26 | **Spec**: [spec.md](file:///d:/Dev/projects/Anime_studio/specs/004-pipeline/spec.md)

**Input**: Feature specification from `specs/004-pipeline/spec.md`

## Summary

Orchestrate the full Anime Studio pipeline: scan an anime library for MKV/ASS pairs, invoke SubtitleRepair and FontResolver, fall back to alass→ffsubsync for subtitle syncing, plan and dispatch MuxJobs via mkvmerge, track trash receipts, and generate `_AnimeStudio_Report.md`. Built as stateless async core services consumed by CLI or TUI, strictly adhering to Hexagonal Architecture.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: pydantic v2, structlog, asyncio, httpx (indirect via FontResolver/hunters)

**Storage**: Filesystem only — MKV/ASS files, font cache (TOML index), trash directory, markdown report

**Testing**: pytest + pytest-asyncio, mocked adapters for unit tests, integration tests with real binaries

**Target Platform**: Windows-first (PowerShell 7+), cross-platform compatible (Linux/macOS)

**Project Type**: CLI service / library (consumed by TUI later)

**Performance Goals**: 12-episode series in <10 minutes, 3 concurrent mux operations

**Constraints**: asyncio.Semaphore(max_concurrent_disk_io) for disk I/O, 120s default timeout, 300s mux timeout

**Scale/Scope**: Single anime series at a time (1–50 episodes), up to 100 fonts per series

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Hexagonal Architecture | ✅ PASS | Pipeline runner lives in `src/core/`, consumes ports/adapters via DI. No TUI imports. |
| II. Cross-Platform | ✅ PASS | All paths via `pathlib.Path`. `shutil.which()` for tool resolution. UTF-8 explicit. |
| III. Async-First I/O | ✅ PASS | Pipeline is async. Disk I/O protected by `asyncio.Semaphore`. Subprocess via `asyncio.create_subprocess_exec`. |
| IV. Structured Errors | ✅ PASS | All failures → domain exceptions or `ToolResult`. No raw tracebacks. |
| V. Plugin Registry | ✅ PASS | FontResolver uses HunterRegistry. No hardcoded hunter lists. |
| VI. Data Safety | ✅ PASS | TrashReceipt for every displaced file. Atomic writes. Dry-run support. |
| VII. Subprocess Lifecycle | ✅ PASS | alass→ffsubsync fallback chain. Timeouts enforced. JSON-first for mkvmerge. |
| VIII. Encoding Guarantees | ✅ PASS | SubtitleRepair handles encoding pipeline. Arabic heuristic in `src/core/encoding.py` (future). |
| IX. Observability | ✅ PASS | structlog at all levels. Cache versioning respected. Progress events emitted. |
| X-bis. Report Generation | ✅ PASS | `_AnimeStudio_Report.md` generated per full run. Overwrite on full, append on partial. |
| X. Test-First | ✅ PASS | Unit tests with mocked adapters. Integration tests gated by `@pytest.mark.integration`. |
| XII. YAGNI | ✅ PASS | No premature abstractions. LibraryScanner and PipelineRunner are purpose-built. |
| XIII. Distribution | ✅ PASS | Tool discovery via DependencyChecker. CRITICAL tools validated at startup. |

All gates pass. No violations to track.

## Project Structure

### Documentation (this feature)

```text
specs/004-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── pipeline_port.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── models/
│   ├── subtitle.py        # SubtitleFile, SyncResult (existing)
│   ├── font.py            # FontQuery, FontAsset (existing)
│   ├── mux.py             # MuxJob, MuxResult (existing)
│   ├── trash.py           # TrashReceipt (existing)
│   ├── report.py          # PipelineReport, EpisodeReport (existing)
│   └── pipeline.py        # [NEW] LibraryScanResult, EpisodeContext
├── ports/
│   └── pipeline.py        # [NEW] PipelinePort protocol
├── core/
│   ├── subtitle_repair.py # repair_ass, extract_fonts (existing)
│   ├── font_resolver.py   # FontResolver (existing)
│   ├── library_scanner.py # [NEW] discover MKV/ASS pairs
│   ├── mux_planner.py     # [NEW] build MuxJob from EpisodeContext
│   ├── report_writer.py   # [NEW] render PipelineReport → markdown
│   └── pipeline_runner.py # [NEW] orchestrate full pipeline
├── adapters/
│   ├── subprocess.py      # SubprocessAdapter (existing)
│   ├── mkvmerge.py        # [NEW] MkvmergeAdapter (mux dispatch)
│   ├── alass.py           # [NEW] AlassAdapter (subtitle sync)
│   ├── ffsubsync.py       # [NEW] FfsubsyncAdapter (sync fallback)
│   ├── filesystem.py      # [NEW] FilesystemAdapter (trash ops, atomic writes)
│   └── dependency_checker.py # DependencyChecker, ToolRegistry (existing)
└── errors.py              # existing error taxonomy

tests/
├── unit/
│   ├── core/
│   │   ├── test_library_scanner.py
│   │   ├── test_mux_planner.py
│   │   ├── test_report_writer.py
│   │   └── test_pipeline_runner.py
│   └── models/
│       └── test_pipeline_models.py
└── integration/
    └── test_pipeline_integration.py
```

**Structure Decision**: Extends existing hexagonal layout. New core services in `src/core/`, new adapters in `src/adapters/`, new models in `src/models/pipeline.py`. All new code follows established patterns.

## Complexity Tracking

No violations. All patterns align with constitution.
