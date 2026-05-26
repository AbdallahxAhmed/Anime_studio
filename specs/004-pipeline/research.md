# Research: Pipeline Orchestration

**Feature**: 004-pipeline | **Date**: 2026-05-26

## R1: Library Scanning Strategy

**Decision**: Synchronous `Path.rglob("*.mkv")` offloaded via `asyncio.to_thread()`.

**Rationale**: Library scanning is disk I/O (stat calls). Constitution III permits synchronous `Path.stat()` for small metadata reads, but bulk scanning with rglob could block. Wrapping in `asyncio.to_thread()` keeps event loop free.

**Alternatives considered**:
- `aiofiles` directory listing: Overkill, adds dependency. Constitution XI favors minimal deps.
- Synchronous scan outside event loop: Acceptable for small libraries but doesn't scale.

## R2: MKV/ASS Pairing Algorithm

**Decision**: Match by stem — `episode.mkv` ↔ `episode.ass`. Case-insensitive comparison. Single-directory scope (ASS must be sibling of MKV).

**Rationale**: This matches real-world anime library conventions. Fansub releases consistently name subtitle files to match episode files. Recursive subdirectory search for ASS files adds complexity with minimal value.

**Alternatives considered**:
- Fuzzy matching (Levenshtein distance): Over-engineered per XII (YAGNI). Would cause false matches.
- Multi-directory scan: Not how anime libraries are structured. Episodes and subs colocate.

## R3: Subtitle Sync Detection

**Decision**: Sync is opt-in, not auto-detected. Pipeline accepts a `sync_enabled: bool` flag. When enabled, every episode's subtitle is synced via the alass→ffsubsync chain.

**Rationale**: Automatic sync detection (comparing audio/subtitle timestamps) requires complex heuristics and risks unnecessary processing. Most fansub files are already synced. Constitution VII mandates fallback chains but doesn't require auto-detection.

**Alternatives considered**:
- Audio-based mismatch detection: Requires ffmpeg audio extraction + analysis. Heavy cost for marginal benefit.
- Per-episode sync flag: Too granular for v1.

## R4: Mux Dispatch Concurrency

**Decision**: Use `asyncio.Semaphore(config.max_concurrent_disk_io)` to gate mkvmerge invocations. Default 3 concurrent. Process episodes sequentially for analysis, concurrently for muxing.

**Rationale**: Constitution III mandates disk I/O protection. Mkvmerge writes large files. 3 concurrent is conservative default that works on both HDD and SSD.

**Alternatives considered**:
- Fully serial: Too slow for 50-episode series.
- Unbounded concurrency: Disk thrashing per Constitution III warning.

## R5: Report Rendering Approach

**Decision**: Pure Python string formatting in `report_writer.py`. No template engine.

**Rationale**: Constitution XII (YAGNI). Report is structured markdown with tables. String formatting + f-strings sufficient. Adding Jinja2/Mako adds dependency for a single output file.

**Alternatives considered**:
- Jinja2 templates: Adds dependency. Constitution XI forbids unnecessary deps.
- `string.Template`: Less readable than f-strings for complex markdown.

## R6: Filesystem Adapter Scope

**Decision**: New `FilesystemAdapter` in `src/adapters/filesystem.py` handles: trash move operations, atomic file writes, directory creation. Implements a `FilesystemPort` protocol.

**Rationale**: Constitution I mandates I/O operations in adapters layer. Trash operations are filesystem mutations. Keeping them behind a port enables unit testing core pipeline without real filesystem.

**Alternatives considered**:
- Inline filesystem ops in pipeline_runner: Violates hexagonal architecture (core doing I/O).
- Reuse existing adapter: No filesystem adapter exists yet.

## R7: MkvmergeAdapter Design

**Decision**: Thin wrapper around `SubprocessAdapter.execute()` that builds mkvmerge command args from `MuxJob`. Uses `mkvmerge -J` for pre-mux validation (JSON identification).

**Rationale**: Constitution VII mandates JSON-first communication. `mkvmerge -J` returns structured JSON. Post-mux, verify via `mkvmerge -i` output.

**Alternatives considered**:
- Raw subprocess calls in pipeline: Violates adapter boundary rule.
- pymkv library: Not in approved dependencies (Constitution XI).

## R8: Alass and Ffsubsync Adapter Design

**Decision**: Each gets a thin adapter wrapping `SubprocessAdapter`. Alass adapter builds `alass <reference> <subtitle> <output>` command. Ffsubsync adapter builds `ffsubsync <reference> -i <subtitle> -o <output>` command.

**Rationale**: Clean separation per adapter. Each returns a `ToolResult`. Pipeline runner handles fallback chain logic in core.

**Alternatives considered**:
- Single "sync adapter" with strategy pattern: Over-engineered. Two simple adapters cleaner per XII.
