# Feature Specification: Pipeline Orchestration

**Feature Branch**: `004-pipeline`

**Created**: 2026-05-26

**Status**: Draft

**Input**: User description: "Phase 3 (Pipeline). Orchestrate the full workflow: scanning the library for MKV/ASS pairs, invoking SubtitleRepair and FontResolver, falling back to alass/ffsubsync via Core Adapters if syncing is needed, planning the MuxJob, dispatching to mkvmerge, tracking trash receipts, and generating the final _AnimeStudio_Report.md markdown report."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Full Library Pipeline Run (Priority: P1)

A user points Anime Studio at an anime library folder. The system automatically discovers all MKV files with matching ASS subtitle files, repairs each subtitle (encoding normalization, structural validation), resolves all required fonts, builds a mux plan per episode, executes mkvmerge to produce finalized MKVs with embedded subtitles and fonts, and writes a comprehensive markdown report summarizing the entire run.

**Why this priority**: This is the core end-to-end workflow that delivers the primary value of Anime Studio — zero-touch anime library preparation.

**Independent Test**: Can be fully tested by pointing the pipeline at a test folder containing 2–3 MKV/ASS pairs and verifying that output MKVs contain correct subtitle and font tracks, original files are trashed safely, and a valid report is generated.

**Acceptance Scenarios**:

1. **Given** a folder with 3 MKV files and 3 matching ASS files, **When** the pipeline runs, **Then** 3 output MKVs are produced with subtitles and fonts muxed in, original ASS files are moved to `.anime_studio_trash/`, and `_AnimeStudio_Report.md` is created at the library root.
2. **Given** a folder with an MKV that has no matching ASS file, **When** the pipeline runs, **Then** that episode is reported as "skipped" in the report and no muxing occurs for it.
3. **Given** a dry-run flag is set, **When** the pipeline runs, **Then** no files are modified, no muxing occurs, but the report is still generated showing what would happen.

---

### User Story 2 - Subtitle Sync Fallback Chain (Priority: P2)

When subtitle timing is mismatched relative to the video, the pipeline attempts to sync using alass first. If alass fails or is unavailable, it falls back to ffsubsync. The sync result is tracked and reported per episode.

**Why this priority**: Subtitle timing mismatches are common in fansub workflows. Automatic syncing adds significant value but depends on optional external tools.

**Independent Test**: Can be tested by providing a deliberately offset ASS file and verifying the pipeline invokes alass, and on simulated failure, falls back to ffsubsync, recording both attempts.

**Acceptance Scenarios**:

1. **Given** an ASS file that needs syncing and alass is available, **When** the pipeline processes it, **Then** alass is invoked, the synced file replaces the original, and the SyncResult records the tool used and offset applied.
2. **Given** alass is unavailable, **When** the pipeline encounters a subtitle needing sync, **Then** ffsubsync is invoked as fallback, and the SyncResult records the fallback tool used.
3. **Given** both alass and ffsubsync fail, **When** the pipeline processes the episode, **Then** the episode is marked as "partial" with an error entry in the report, and the original subtitle is left untouched.

---

### User Story 3 - Trash Receipt Tracking (Priority: P3)

When the pipeline replaces original subtitle files or original MKV episodes, the originals are safely moved to `.anime_studio_trash/` with deterministic naming. Trash receipts are recorded per operation and included in the pipeline report.

**Why this priority**: Data safety is constitutionally mandated. Trash tracking ensures users can recover originals within the 30-day retention window.

**Independent Test**: Can be tested by running the pipeline on a single episode, verifying the original file exists in `.anime_studio_trash/` with the correct expiration-prefixed filename, and confirming the trash receipt appears in the report.

**Acceptance Scenarios**:

1. **Given** a pipeline run replaces an original ASS file, **When** the operation completes, **Then** the original is moved to `.anime_studio_trash/EXP-{date}-{filename}` and a TrashReceipt is generated with correct timestamps.
2. **Given** `.anime_studio_trash/` does not exist, **When** a trash operation occurs, **Then** the directory is created automatically.

---

### User Story 4 - Pipeline Report Generation (Priority: P4)

After every full pipeline run, a structured markdown report (`_AnimeStudio_Report.md`) is generated at the library root. The report includes run metadata, per-episode status, per-font resolution details, applied rules, and genuine misses with audit trails.

**Why this priority**: Report generation is constitutionally mandated (Principle X-bis) and provides essential observability for the user.

**Independent Test**: Can be tested by running the pipeline and validating the generated report against a known schema — checking presence of timestamp, duration, per-episode rows with status symbols, and font resolution details.

**Acceptance Scenarios**:

1. **Given** a full pipeline run completes, **When** the report is generated, **Then** it contains: run timestamp, total duration, per-episode table with ✓/⚠/✗ status, per-font source and cache hit/miss, and genuine misses list.
2. **Given** a partial/incremental run, **When** the report is generated, **Then** it appends to the existing report with a clearly delimited section header rather than overwriting.
3. **Given** the report already exists from a previous full run, **When** a new full run completes, **Then** the old report is overwritten with the new canonical report.

---

### Edge Cases

- What happens when the library folder contains zero MKV files? → Pipeline completes immediately with an empty report.
- What happens when an ASS file has unrecoverable encoding corruption? → Episode marked "failed", EncodingRepairError logged, pipeline continues to next episode.
- What happens when mkvmerge fails for a specific episode? → Episode marked "failed", MuxResult records the error, pipeline continues.
- What happens when all fonts for an episode are missing? → Episode marked "partial" (subtitles muxed without fonts), missing fonts listed in report.
- What happens when disk space is insufficient during mux? → mkvmerge fails, caught as ToolExecutionError, episode marked "failed".
- What happens when the user interrupts the pipeline mid-run? → Graceful cancellation via asyncio CancelledError, partial report generated.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST scan a user-provided library directory recursively for `.mkv` files and discover matching `.ass` subtitle files by filename proximity (same stem or known naming conventions).
- **FR-002**: System MUST invoke `SubtitleRepair.repair_ass()` on each discovered ASS file to validate structure and normalize encoding before further processing.
- **FR-003**: System MUST invoke `FontResolver.resolve()` for each font referenced in the repaired ASS content to acquire all required fonts.
- **FR-004**: System MUST attempt subtitle synchronization via the alass→ffsubsync fallback chain when sync is requested or timing mismatch is detected, using the existing `SubprocessAdapter` and `ToolRegistry`.
- **FR-005**: System MUST construct a `MuxJob` per episode containing the episode path, repaired subtitle path, resolved fonts list, and output path.
- **FR-006**: System MUST dispatch each `MuxJob` to `mkvmerge` via the `SubprocessAdapter`, respecting the `disk_io_semaphore` (max concurrent operations from `AppConfig.max_concurrent_disk_io`).
- **FR-007**: System MUST generate a `TrashReceipt` for every original file displaced during the pipeline and execute the actual file move to `.anime_studio_trash/`.
- **FR-008**: System MUST generate `_AnimeStudio_Report.md` at the library root after each full run, conforming to Principle X-bis.
- **FR-009**: System MUST support a `dry_run` mode where the full pipeline executes analysis and planning but skips all file mutations (muxing, trashing).
- **FR-010**: System MUST handle individual episode failures gracefully — one failed episode MUST NOT abort the remaining pipeline.
- **FR-011**: System MUST respect the `asyncio.Semaphore` for disk I/O operations (muxing, extraction) to prevent disk thrashing per Constitution Principle III.
- **FR-012**: System MUST collect timing metrics (duration_ms) for all operations and include them in the pipeline report.
- **FR-013**: System MUST log all operations via `structlog` at appropriate levels per Constitution Principle IX.

### Key Entities

- **LibraryScan**: Represents the discovered MKV/ASS pairs from a directory scan — episode path, subtitle path, anime title.
- **EpisodeContext**: Aggregates all intermediate results for one episode — repaired subtitle, resolved fonts, sync result, mux job, mux result, trash receipts.
- **PipelineReport**: Already defined in `src/models/report.py` — aggregates all episode reports with run metadata.
- **MuxJob / MuxResult**: Already defined in `src/models/mux.py`.
- **TrashReceipt**: Already defined in `src/models/trash.py`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Pipeline processes a 12-episode anime series (12 MKV + 12 ASS files) end-to-end in under 10 minutes on standard hardware.
- **SC-002**: 100% of processed episodes produce valid MKV output with correct subtitle and font tracks when all fonts are available.
- **SC-003**: Every displaced original file has a corresponding trash receipt with correct expiration date.
- **SC-004**: Generated report accurately reflects the status of every episode (✓/⚠/✗) with zero false positives.
- **SC-005**: Pipeline handles 3+ concurrent mux operations without disk thrashing or data corruption, respecting the configured semaphore limit.
- **SC-006**: Individual episode failure does not affect processing of remaining episodes — pipeline resilience is 100%.
- **SC-007**: Dry-run mode produces identical report content (minus actual file changes) without modifying any files on disk.

## Assumptions

- The anime library follows a standard structure where MKV and ASS files share the same parent directory and similar filenames (same stem or well-known naming patterns).
- The user has already configured `config.toml` with font cache path and external tool paths (or tools are discoverable via the Tool Registry).
- External tools (mkvmerge, ffmpeg, mkvextract) are installed and available (CRITICAL classification from DependencyChecker).
- Font resolution may take variable time depending on network conditions and hunter availability — the pipeline tolerates slow font resolution gracefully.
- The pipeline runs as a CLI-invocable service, not directly from the TUI (TUI integration is a separate future concern).
