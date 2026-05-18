<!--
  ============================================================================
  SYNC IMPACT REPORT
  ============================================================================
  Version change: 1.1.0 → 1.4.0 (3 MINOR bumps combined)

  Amended principles:
    V.   Plugin Registry Architecture
         + Circuit Breaker & Rate Limiting mandate for HunterProtocol
    IX.  Observability & Structured Logging
         + Cache Versioning mandate for persistent cache files

  Added sections:
    X-bis. Pipeline Report Generation (new principle, v1.1.0)
    XIII.  Distribution & External Dependencies (new principle, v1.2.0)
           + Tool Discovery Order (Windows-first, 5-step)
           + Binary classification (CRITICAL / OPTIONAL / ALWAYS AVAILABLE)
           + Distribution via install.ps1 + run.bat/run.ps1
           + mpv-config independence mandate (v1.3.0)
           + sub-fonts-dir FORBIDDEN, MKV muxing only (v1.3.0)
           + Storage layout: volatile C: + permanent D: (v1.4.0)

  Removed sections: none

  Templates requiring updates:
    ✅ plan-template.md      — Constitution Check now covers V (circuit
                               breaker), IX (cache versioning), X-bis
                               (report generation), XIII (distribution)
    ✅ spec-template.md      — No update needed
    ✅ tasks-template.md     — Tool discovery + storage layout may spawn
                               new task types; no structural template change
    ✅ checklist-template.md — No update needed

  Migration notes:
    - HunterProtocol implementations MUST add `rate_limit` and
      `circuit_breaker_threshold` fields
    - `src/config.py` MUST define `CACHE_VERSION` constant
    - Pipeline runner MUST produce `_AnimeStudio_Report.md`
    - Tool discovery MUST follow 5-step Windows-first order
    - Storage paths: %APPDATA% for config, D:\Entertainment for data
    - mpv-config MUST NOT be depended on or modified
    - sub-fonts-dir usage is FORBIDDEN
    - font_cache on D: is self-describing, no config dependency

  Follow-up TODOs:
    - Update HunterProtocol definition in src/ports/font_hunter.py
    - Add CACHE_VERSION to src/config.py
    - Implement report generation in pipeline runner
    - Implement 5-step tool discovery in src/adapters/
    - Create install.ps1 and run.bat/run.ps1
    - Implement storage layout with C:/D: split
  ============================================================================
-->

# Anime Studio v3 Constitution

## Core Principles

### I. Separation of Concerns — Hexagonal Architecture

The monolithic coupling of UI, scraping, and subprocess management is the
root cause of every legacy failure. The v3 architecture MUST enforce strict
layer separation using a Hexagonal (Ports & Adapters) pattern with exactly
five bounded domains:

1. **Domain Models** (`src/models/`): Pure data structures (Pydantic
   `BaseModel` or `@dataclass`) with zero I/O, zero imports from other
   layers. These define `SubtitleFile`, `FontAsset`, `MuxJob`,
   `HunterResult`, and all forensic pipeline intermediates.
2. **Core Forensics** (`src/core/`): Stateless, async service functions
   that implement business logic — subtitle syncing, font matching, ASS
   repair, mux planning. Core services accept and return Domain Models.
   They MUST NOT import from the TUI, CLI, or Hunter layers.
3. **Hunter Registry** (`src/hunters/`): A plugin-based registry of font
   acquisition sources (web scrapers, API clients). Each hunter implements
   a `HunterProtocol` and is discovered at runtime via entry-points or
   explicit registration. The registry MUST NOT be hardcoded; adding a
   hunter MUST NOT require modifying existing code (Open/Closed Principle).
4. **Infrastructure / Adapters** (`src/adapters/`): All side-effectful
   operations — subprocess calls (`ffmpeg`, `mkvmerge`, `alass`,
   `ffsubsync`, `ots-sanitize`), filesystem access, network I/O via
   `httpx`. Adapters implement port interfaces defined in `src/ports/`.
5. **Presentation** (`src/tui/`): The Textual TUI application. The TUI
   layer MUST be a pure consumer of Core services via message-passing and
   async workers. It MUST NOT contain business logic, subprocess calls, or
   direct filesystem manipulation.

**Rationale**: Enforcing these boundaries guarantees that forensic engines
can be tested without a running TUI, hunters can be developed in isolation,
and the TUI can be replaced (e.g., with a web frontend) without touching
core logic.

### II. Cross-Platform & Windows-First Compatibility

The primary runtime is Windows (Windows Terminal / PowerShell 7+), but all
code MUST run unmodified on Linux and macOS. The following rules are
NON-NEGOTIABLE:

- **Pathlib Everywhere**: All file path construction and manipulation MUST
  use `pathlib.Path`. Raw string concatenation with `/` or `\\` separators
  is FORBIDDEN. Path constants MUST be defined as `Path` objects.
- **Executable Resolution**: Subprocess executables MUST be resolved via
  `shutil.which()` before invocation. The caller MUST NOT hardcode `.exe`
  extensions or assume PATH resolution behavior.
- **UTF-8 Default**: All `open()` calls MUST explicitly pass
  `encoding="utf-8"` (or the correct target encoding when intentionally
  handling legacy codepages). Relying on the system default encoding is
  FORBIDDEN. On Python 3.15+, `sys.flags.utf8_mode` may be assumed, but
  explicit encoding MUST still be passed for backward compatibility.
- **Line Endings**: Text files MUST be opened with `newline=""` when
  precise line-ending control is required (e.g., ASS subtitle repair).
- **Temp Directories**: Use `tempfile.mkdtemp()` or
  `tempfile.TemporaryDirectory()` instead of hardcoded `/tmp` or
  `%TEMP%` paths.
- **Console Output**: Never assume ANSI escape code support. The Textual
  framework handles terminal capability detection. Direct `print()`
  with ANSI codes outside the TUI is FORBIDDEN.

### III. Async-First I/O

Every I/O operation — network, filesystem, subprocess — MUST be
non-blocking. The legacy `urllib` + synchronous subprocess pattern that
froze the UI is FORBIDDEN.

- **Network**: All HTTP requests MUST use `httpx.AsyncClient` with
  explicit timeouts, connection pooling, and retry policies. Raw `urllib`,
  `requests`, or synchronous `httpx` calls are FORBIDDEN.
- **Subprocess**: All external tool invocations MUST use
  `asyncio.create_subprocess_exec()` (or the adapter abstraction wrapping
  it). Blocking `subprocess.run()` / `subprocess.Popen()` with
  synchronous `.communicate()` is FORBIDDEN outside of test fixtures.
- **Filesystem**: For large file operations (reading MKV metadata, bulk
  font scanning), use `asyncio.to_thread()` to offload blocking calls.
  Small metadata reads (`Path.stat()`, `Path.exists()`) MAY remain
  synchronous when called outside the TUI event loop.
- **Concurrency Model**: The application MUST use a single `asyncio` event
  loop. Textual's built-in worker system (`self.run_worker()`) MUST be
  used for background tasks within the TUI. Manual thread creation is
  FORBIDDEN unless wrapping a fundamentally blocking C library.

### IV. Structured Error Handling & Actionable Failures

Raw tracebacks MUST NEVER be displayed to the user. Every failure MUST be
translated into a structured, actionable error.

- **ToolResult Pattern**: All subprocess adapter calls MUST return a
  `ToolResult` model containing: `success: bool`, `exit_code: int`,
  `stdout: str`, `stderr: str`, `tool_name: str`, `duration_ms: float`,
  and `suggestion: str | None`. The `suggestion` field MUST contain a
  human-readable remediation hint (e.g., "alass failed — try installing
  alass v2.0+ or check subtitle encoding").
- **Error Taxonomy**: Define a hierarchy of domain exceptions in
  `src/errors.py`:
  - `AnimeStudioError` (base)
    - `ToolNotFoundError` (external binary missing)
    - `ToolExecutionError` (binary ran but returned non-zero)
    - `EncodingRepairError` (ASS/subtitle encoding unfixable)
    - `FontMatchError` (no font match found after all hunters exhausted)
    - `MuxIntegrityError` (MKV structure validation failed post-mux)
    - `HunterError` (font source unreachable or rate-limited)
    - `ConfigurationError` (invalid user config)
- **Boundary Rule**: Exceptions MUST be caught at adapter boundaries and
  converted to `ToolResult` or domain-specific errors. Core services MUST
  raise domain exceptions, never `OSError`, `httpx.HTTPError`, or
  `subprocess.CalledProcessError` directly.
- **TUI Contract**: The TUI MUST present errors via styled notification
  widgets (Textual `Notify` / modal dialogs), never via `stderr` dumps.

### V. Plugin Registry Architecture

The legacy hardcoded dictionaries that caused `KeyError` crashes are
FORBIDDEN. All extensible collections MUST use a Registry pattern.

- **Hunter Registry**: Font acquisition sources MUST implement the
  `HunterProtocol` (a `typing.Protocol` or ABC):
  ```
  class HunterProtocol(Protocol):
      name: str
      priority: int
      rate_limit: float                  # max requests/sec to this source
      circuit_breaker_threshold: int     # consecutive failures before open (default: 3)
      async def search(self, query: FontQuery) -> list[HunterResult]: ...
      async def download(self, result: HunterResult) -> FontPayload: ...
      def supports(self, query: FontQuery) -> bool: ...
  ```
  Hunters are registered via a `HunterRegistry` that supports:
  - Runtime registration (`registry.register(hunter)`)
  - Priority-ordered iteration
  - Graceful skip on individual hunter failure (the registry continues to
    the next hunter)
- **Circuit Breaker & Rate Limiting**: Every `HunterProtocol`
  implementation MUST declare:
  - `rate_limit: float` — maximum requests per second to this source
  - `circuit_breaker_threshold: int` — consecutive failures before
    the circuit opens (default: 3)

  The `HunterRegistry` MUST track failure counts per hunter per session.
  When a hunter's circuit is open, the registry MUST skip it silently
  and log a WARNING. The circuit resets at session start.
- **Source Registry**: Subtitle/media source labels (e.g., streaming
  services, fansub groups) MUST be loaded from a TOML/YAML config file at
  startup, never hardcoded. Adding a new source MUST NOT require code
  changes.
- **Tool Registry**: External tool binaries (`ffmpeg`, `mkvmerge`,
  `alass`, `ffsubsync`, `ots-sanitize`, `fontTools`) MUST be registered
  with their resolved paths at startup via `shutil.which()`. Missing
  optional tools MUST be logged as warnings; missing required tools MUST
  raise `ToolNotFoundError` with installation instructions.

### VI. Data Safety & Non-Destructive Operations

User data is sacred. The system MUST NEVER destroy original files.

- **Trash Directory**: When an operation would overwrite or remove an
  original subtitle file, the original MUST be moved to a
  `.anime_studio_trash/` directory (sibling to the source file) with a
  timestamped suffix (e.g., `original.ass.2025-05-17T103000`).
- **Atomic Writes**: Output files (muxed MKVs, repaired ASS files) MUST
  be written to a temporary file first, then atomically renamed to the
  target path. Partial writes MUST NOT leave corrupted files.
- **Dry-Run Mode**: All destructive operations (muxing, font attachment,
  subtitle replacement) MUST support a `--dry-run` flag that reports what
  would change without modifying any files.
- **Idempotency**: Running the same operation twice on the same input MUST
  produce the same output without duplicating attachments or corrupting
  existing subtitle tracks.

### VII. Subprocess Lifecycle Management

External tools are the backbone of Anime Studio. Their execution MUST be
robust, observable, and recoverable.

- **Fallback Chains**: Critical operations MUST define ordered fallback
  strategies. Example for subtitle syncing:
  1. Attempt `alass` (fast, reference-based)
  2. On failure → attempt `ffsubsync` with VAD pipeline
  3. On failure → report structured error with both tool outputs
- **Timeout Enforcement**: Every subprocess MUST have a configurable
  timeout (default: 120s for sync operations, 300s for muxing). On
  timeout, the process MUST be killed and a `ToolExecutionError` raised.
- **JSON-First Communication**: Where tools support it (e.g.,
  `mkvmerge -J`), MUST use structured JSON output. Parse results into
  domain models immediately.
- **Stderr Capture**: All subprocess stderr MUST be captured and included
  in `ToolResult` for diagnostics, but MUST NOT be forwarded to the
  user's terminal.

### VIII. Encoding Guarantees

Encoding bugs are the #1 cause of subtitle corruption. The following
pipeline is MANDATORY for all subtitle ingestion:

1. **Detection**: Use `charset_normalizer` (preferred) or `chardet` to
   detect source encoding. MUST NOT assume UTF-8.
2. **Normalization**: Transcode all detected encodings to UTF-8 with BOM
   stripped. Handle `cp1252`, `UTF-16 LE/BE`, `Shift_JIS`, `EUC-KR`, and
   `ISO-8859-1` explicitly.
3. **Line Ending Repair**: Normalize to `\r\n` for ASS format
   compatibility (ASS spec mandates Windows line endings).
4. **Validation**: After transcoding, parse the ASS file with a lenient
   parser to verify structural integrity (section headers, dialogue line
   counts). Log warnings for recoverable issues; raise
   `EncodingRepairError` for unrecoverable corruption.
5. **Round-Trip Safety**: The encoding pipeline MUST be idempotent —
   running it on an already-repaired file MUST produce identical output.

### IX. Observability & Structured Logging

Every operation MUST be traceable for debugging without exposing internals
to end users.

- **Structured Logging**: Use Python's `logging` module with
  `structlog` for JSON-formatted log output. Every log entry MUST include:
  `timestamp`, `level`, `module`, `event`, and relevant context fields
  (e.g., `file_path`, `tool_name`, `duration_ms`).
- **Log Levels**:
  - `DEBUG`: Subprocess commands, raw stdout/stderr, internal state
  - `INFO`: Operation start/complete, file counts, hunter results
  - `WARNING`: Fallback triggered, optional tool missing, recoverable
    encoding issue
  - `ERROR`: Operation failed, tool crashed, unrecoverable error
- **Log Destination**: Logs MUST be written to a rotating file
  (`~/.anime_studio/logs/`). The TUI MUST NOT display raw log lines;
  instead, it MUST surface a curated activity feed derived from `INFO`+
  events.
- **Cache Versioning**: Any persistent cache file written by
  Anime Studio MUST include a top-level `cache_version` field
  matching the constant `CACHE_VERSION` defined in `src/config.py`.
  On load, if `cache_version` mismatches, the cache MUST be
  deleted and rebuilt from scratch. Silent reads of stale cache
  are FORBIDDEN.
- **Operation Tracking**: Long-running operations (muxing, bulk font
  search) MUST emit progress events that the TUI can render as progress
  bars or spinners.

### X-bis. Pipeline Report Generation

Every full pipeline run MUST produce a structured Markdown report
saved to the anime library root as `_AnimeStudio_Report.md`.
The report MUST include:
- Run timestamp and duration
- Per-episode status: ✓ complete / ⚠ partial / ✗ failed
- Per-font status: source used, layer that found it, cache hit/miss
- Any Rule applications (Rule 2 escalations, Rule 3 patches)
- Genuine misses with full audit trail (what was searched, why failed)

The report MUST be overwritten on each full pipeline run (single
canonical report, not accumulated). Partial/incremental runs MUST
append to the existing report with a clearly delimited section header.

### X. Test-First Discipline

Tests are NOT optional. The following testing mandate applies:

- **Unit Tests**: All Core Forensics functions MUST have unit tests with
  mocked adapters. Minimum coverage target: 85% for `src/core/`.
- **Integration Tests**: Subprocess adapters MUST have integration tests
  that run against real binaries (gated behind a `pytest` marker
  `@pytest.mark.integration` for CI environments without tools installed).
- **Contract Tests**: Hunter protocol compliance MUST be verified via
  contract tests that assert the `HunterProtocol` interface.
- **Encoding Tests**: The encoding pipeline MUST include tests with real
  sample files in `cp1252`, `UTF-16 LE`, `Shift_JIS`, and `UTF-8 BOM`
  encodings.
- **Framework**: `pytest` with `pytest-asyncio` for async tests. Test
  files MUST mirror source structure under `tests/`.
- **No Mocking Core Logic**: Core forensic functions MUST NOT be mocked
  in their own unit tests. Only adapters (I/O boundaries) are mocked.

### XI. Dependency Isolation & Vendoring Policy

The dependency tree MUST be minimal, audited, and pinned.

- **Package Manager**: `uv` (preferred) or `pip` with a locked
  `requirements.lock` (or `uv.lock`). Unpinned dependencies are
  FORBIDDEN in production.
- **Core Dependencies** (approved):
  - `textual` — TUI framework
  - `httpx` — async HTTP client
  - `pydantic` — data validation and settings
  - `fonttools` — font introspection and repair
  - `charset-normalizer` — encoding detection
  - `structlog` — structured logging
  - `tomli` / `tomllib` — configuration parsing
- **Conditional Dependencies**: `alass`, `ffsubsync`, `ots-sanitize` are
  external binaries, NOT Python packages. They MUST be resolved at runtime
  via the Tool Registry, never imported.
- **Vendoring**: No vendoring. All dependencies MUST be installable via
  `pip` / `uv` from PyPI.
- **Python Version**: Python 3.11+ is REQUIRED. Code MUST use modern
  syntax: `match` statements, `type` aliases (3.12+), `ExceptionGroup`
  where beneficial, and `asyncio.TaskGroup` for structured concurrency.

### XII. Simplicity & YAGNI

Complexity MUST be justified. Every abstraction MUST earn its existence.

- **No Premature Abstraction**: Do not create interfaces, factories, or
  registries for components that currently have exactly one implementation.
  Exception: the Hunter Registry, which is designed for extensibility from
  day one.
- **Flat Over Nested**: Prefer flat module structures. If a package has
  only one module, it SHOULD be a single file, not a package.
- **Configuration**: Use a single `config.toml` file with Pydantic
  `BaseSettings` for validation. Environment variable overrides MUST
  follow `ANIME_STUDIO_` prefix convention.
- **No ORM**: Font and subtitle metadata are transient, not persisted to a
  database. Use Pydantic models, not SQLAlchemy.
- **Feature Flags**: Features under development MUST be gated behind
  config flags, not `if False:` blocks or commented-out code.

### XIII. Distribution & External Dependencies

#### Tool Discovery

External binary resolution MUST follow this Windows-first discovery
order. The first match wins:

1. `~\scoop\shims\<tool>.exe`
2. `~\scoop\apps\<tool>\current\**\<tool>.exe`
3. `C:\Program Files\mpv\<tool>.exe`
4. `C:\Program Files\<Tool>\**\<tool>.exe`
5. `shutil.which(<tool>)`

On non-Windows platforms, only step 5 applies.

Binary classifications:

| Classification | Binaries | Behavior |
|----------------|----------|----------|
| **CRITICAL** (app refuses to start) | `ffmpeg`, `mkvmerge`, `mkvextract` | Raise `ToolNotFoundError` with install instructions |
| **OPTIONAL** (reduced features + WARNING) | `alass`, `ots-sanitize`, `yt-dlp` | Log WARNING, disable dependent features |
| **ALWAYS AVAILABLE** (via `uv`) | `ffsubsync`, `fonttools`, `charset-normalizer` | Installed as Python packages, no binary resolution needed |

#### Distribution

- **Installer**: `install.ps1` handles `uv` + `winget` setup
- **Launchers**: `run.bat` / `run.ps1` activate venv and invoke entry point
- **Virtual Environment**: `uv` managed at
  `D:\Entertainment\.anime_studio\venv\`

#### mpv-config Independence

`mpv-config` (`github.com/AbdallahxAhmed/mpv-config`) is an independent
project. Anime Studio v3 MUST NOT depend on it or modify it. Its binaries
(e.g., `ffmpeg`, `mpv`) are discovery candidates only (step 3 above).

- `sub-fonts-dir` is **FORBIDDEN** — known mpv bugs confirmed.
- MKV muxing via `mkvmerge` is the **ONLY** font output method.
- No `fonts\` folder creation. No mpv config modification.

#### Storage Layout

Storage is designed for volatile `C:` + permanent `D:` separation:

**Volatile** (recreatable on Windows reinstall):
- `%APPDATA%\AnimeStudio\config.toml` — user preferences only
- If missing on startup: recreated from defaults silently.

**Permanent** (survives Windows reinstall):
```text
D:\Entertainment\.anime_studio\
├── font_cache\        # all downloaded fonts, NEVER deleted
├── font_library.toml  # index with CACHE_VERSION = "3.0"
├── logs\              # pipeline history
└── venv\              # uv managed Python environment
```

**Resolution rule**: if `font_cache` exists on `D:` → use it
regardless of whether `config.toml` exists on `C:`.
Cache is self-describing — no config needed to find it.

## Technology Stack & Constraints

| Component           | Technology                     | Rationale                                          |
|---------------------|--------------------------------|----------------------------------------------------|
| Language            | Python 3.11+                   | `asyncio.TaskGroup`, `tomllib`, `match` statements |
| TUI Framework       | Textual 1.x                   | Async-native, CSS styling, Nerd Font support       |
| HTTP Client         | httpx (async)                  | HTTP/2, connection pooling, timeout control        |
| Data Validation     | Pydantic v2                    | Performance, JSON Schema export, settings mgmt     |
| Font Introspection  | fontTools                      | Industry standard for OpenType/TrueType parsing    |
| Encoding Detection  | charset-normalizer             | Better accuracy than chardet, maintained            |
| Logging             | structlog + stdlib logging     | Structured JSON logs, zero-config dev mode         |
| Configuration       | TOML (tomllib / tomli)         | Human-readable, stdlib in 3.11+                    |
| Testing             | pytest + pytest-asyncio        | De-facto standard, async support                   |
| Package Management  | uv (preferred) or pip          | Speed, lockfile support                            |
| Subprocess Sync     | alass → ffsubsync (fallback)   | Quality-ordered fallback chain                     |
| Font Sanitization   | ots-sanitize (fallback)        | Catches fontTools-unrepairable corruption           |
| Muxing              | mkvmerge (MKVToolNix)          | Industry standard for Matroska operations          |

## Forbidden Patterns

The following patterns are EXPLICITLY FORBIDDEN and MUST be rejected in
code review:

| Pattern                              | Replacement                                        |
|--------------------------------------|----------------------------------------------------|
| `os.path.join()` / string paths      | `pathlib.Path` operators                           |
| `urllib.request` / `requests`        | `httpx.AsyncClient`                                |
| `subprocess.run()` (blocking)        | `asyncio.create_subprocess_exec()`                 |
| `open()` without `encoding=`        | `open(encoding="utf-8")` (or explicit encoding)   |
| Hardcoded dicts for extensible sets  | Registry / Plugin pattern                          |
| `print()` for user output            | Textual widgets / `structlog` for logs             |
| Bare `except:` or `except Exception` | Specific exception types + `ToolResult` wrapping   |
| `os.system()`                        | `asyncio.create_subprocess_exec()`                 |
| Global mutable state                 | Dependency injection via constructor / config      |
| `time.sleep()` in async code         | `asyncio.sleep()`                                  |
| Hardcoded `.exe` in binary names     | `shutil.which()` resolution                        |
| `curses` or direct `rich` usage      | Textual TUI framework exclusively                  |
| `sys.exit()` in library code         | Raise domain exception; only CLI entry point exits |

## Development Workflow

### Branch Strategy

- `main` — stable, release-ready code only
- `feature/###-description` — all development work
- Merge via pull request with passing CI

### Commit Convention

All commits MUST follow Conventional Commits format:

```
<type>(<scope>): <description>

Types: feat, fix, refactor, test, docs, chore, ci
Scopes: core, tui, hunters, adapters, models, config
```

### Code Quality Gates

Every pull request MUST pass:

1. `ruff check .` — linting (zero warnings)
2. `ruff format --check .` — formatting
3. `pytest tests/unit/` — unit tests (100% pass)
4. `mypy src/ --strict` — type checking (zero errors)
5. Constitution compliance review (manual or automated)

### File Organization

```text
anime_studio/
├── src/
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── app.py               # Textual App subclass
│   ├── config.py            # Pydantic BaseSettings
│   ├── errors.py            # Exception taxonomy
│   ├── models/              # Pure data models (Pydantic)
│   │   ├── subtitle.py
│   │   ├── font.py
│   │   ├── mux.py
│   │   └── tool_result.py
│   ├── ports/               # Abstract interfaces (Protocols)
│   │   ├── subprocess.py
│   │   ├── font_hunter.py
│   │   └── filesystem.py
│   ├── core/                # Business logic (stateless, async)
│   │   ├── subtitle_sync.py
│   │   ├── font_match.py
│   │   ├── ass_repair.py
│   │   ├── mux_planner.py
│   │   └── encoding.py
│   ├── adapters/            # I/O implementations
│   │   ├── ffmpeg.py
│   │   ├── mkvmerge.py
│   │   ├── alass.py
│   │   ├── ffsubsync.py
│   │   ├── ots_sanitize.py
│   │   └── filesystem.py
│   ├── hunters/             # Font acquisition plugins
│   │   ├── registry.py
│   │   ├── base.py
│   │   └── sources/
│   │       ├── google_fonts.py
│   │       ├── dafont.py
│   │       └── ...
│   └── tui/                 # Textual UI components
│       ├── screens/
│       ├── widgets/
│       └── styles/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── config.toml
├── pyproject.toml
└── README.md
```

## Governance

This constitution is the supreme authority for all architectural and
coding decisions in Anime Studio v3. It supersedes README files, inline
comments, and verbal agreements.

- **Amendment Process**: Any change to this constitution MUST be:
  1. Proposed as a diff in a dedicated PR
  2. Reviewed and approved by the project maintainer
  3. Accompanied by a migration plan if the change affects existing code
  4. Version-bumped according to semantic versioning (see below)
- **Compliance Enforcement**: All pull requests MUST include a
  "Constitution Check" section confirming compliance with relevant
  principles. Reviewers MUST verify compliance before approving.
- **Versioning**: This constitution follows semantic versioning:
  - **MAJOR**: Backward-incompatible principle removal or redefinition
  - **MINOR**: New principle added or existing principle materially expanded
  - **PATCH**: Wording clarification, typo fix, non-semantic refinement
- **Conflict Resolution**: When a principle conflicts with a practical
  implementation need, the conflict MUST be documented in the Complexity
  Tracking table (plan-template.md) with justification for the deviation.
- **Guidance File**: For runtime development guidance and quick-reference
  rules, consult `AGENTS.md` at the repository root.

**Version**: 1.4.0 | **Ratified**: 2026-05-17 | **Last Amended**: 2026-05-18
