# Feature Specification: Domain Models Layer

**Feature Branch**: `001-domain-models`

**Created**: 2026-05-17

**Status**: Draft

**Input**: User description: "Build the complete domain models for Anime Studio v3. Pure Pydantic v2 BaseModel classes — zero I/O, zero imports from other project layers."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define Font Acquisition Data Structures (Priority: P1)

A developer building the font-matching pipeline needs data structures to represent font queries, search results, and resolved font assets. These models carry metadata through every layer — from hunter search to mux attachment — without coupling to any I/O or service layer.

**Why this priority**: Font matching is the core value proposition of Anime Studio. Every other pipeline stage (subtitle repair, muxing, reporting) depends on well-defined font data structures.

**Independent Test**: Can be fully tested by instantiating `FontQuery`, `FontAsset`, and `HunterResult` with valid and invalid data, verifying Pydantic validation fires correctly, and confirming serialization round-trips to JSON without data loss.

**Acceptance Scenarios**:

1. **Given** valid font metadata, **When** a `FontAsset` is created, **Then** all fields are populated and the model is immutable (frozen).
2. **Given** a `FontQuery` with an anime title and requested font name, **When** serialized to JSON, **Then** all `Path` fields serialize as POSIX strings and deserialize back to `Path` objects.
3. **Given** invalid data (e.g., negative `layer_found`), **When** model construction is attempted, **Then** Pydantic validation raises a `ValidationError` with a clear message.

---

### User Story 2 - Define Subtitle Processing Data Structures (Priority: P1)

A developer working on subtitle ingestion and sync needs models to represent subtitle files (with detected encoding, line endings, required fonts) and sync operation results (tool used, fallback status, timing).

**Why this priority**: Subtitle processing is the second core pipeline — encoding detection, repair, and sync all flow through these models.

**Independent Test**: Can be fully tested by constructing `SubtitleFile` and `SyncResult` models with representative data, validating constraints (e.g., `fonts_required` is a list of strings), and verifying immutability.

**Acceptance Scenarios**:

1. **Given** a subtitle file with detected encoding `cp1252`, **When** a `SubtitleFile` model is created, **Then** `encoding_detected` is stored exactly and `is_repaired` defaults to `False`.
2. **Given** a sync operation that used `alass` with `ffsubsync` fallback, **When** a `SyncResult` is created, **Then** both `tool_used` and `tool_fallback_used` fields are populated.

---

### User Story 3 - Define Muxing Pipeline Data Structures (Priority: P1)

A developer building the mux planner needs models to describe a mux job (inputs, fonts, dry-run flag) and its result (output path, attached font count, warnings).

**Why this priority**: Muxing is the final pipeline stage — every episode must produce a valid MKV with correctly attached fonts and subtitles.

**Independent Test**: Can be fully tested by constructing `MuxJob` and `MuxResult` with valid data, checking that `fonts` accepts a list of `FontAsset` models, and verifying `dry_run` defaults to `False`.

**Acceptance Scenarios**:

1. **Given** an episode with 3 fonts and a subtitle, **When** a `MuxJob` is created, **Then** `fonts` contains exactly 3 `FontAsset` instances and `dry_run` is `False` by default.
2. **Given** a successful mux, **When** `MuxResult` is created, **Then** `success` is `True`, `fonts_attached` equals the count of input fonts, and `warnings` is an empty list.

---

### User Story 4 - Define Tool Execution Result (Priority: P1)

A developer wrapping external tools (ffmpeg, mkvmerge, alass, etc.) needs a universal result model that captures exit code, stdout, stderr, timing, and a human-readable remediation suggestion.

**Why this priority**: Constitution Principle IV mandates the `ToolResult` pattern for every subprocess adapter call. This is a cross-cutting dependency.

**Independent Test**: Can be fully tested by creating `ToolResult` instances for success and failure cases, verifying `suggestion` is optional (nullable), and confirming all fields serialize cleanly.

**Acceptance Scenarios**:

1. **Given** a successful tool run, **When** `ToolResult` is created with `exit_code=0`, **Then** `success` is `True` and `suggestion` is `None`.
2. **Given** a failed tool run, **When** `ToolResult` is created with a non-zero exit code and a suggestion string, **Then** the suggestion contains actionable remediation text.

---

### User Story 5 - Define Pipeline Reporting Data Structures (Priority: P2)

A developer building the pipeline runner needs models for per-episode status, per-episode reports, and the overall pipeline report that gets written as `_AnimeStudio_Report.md`.

**Why this priority**: Constitution Principle X-bis mandates structured pipeline reports. These models define the schema but are consumed only after the core pipeline (font, subtitle, mux) models exist.

**Independent Test**: Can be fully tested by constructing `EpisodeReport` and `PipelineReport` with mixed statuses (COMPLETE, PARTIAL, FAILED, SKIPPED) and verifying aggregation logic (total fonts found, genuine misses list).

**Acceptance Scenarios**:

1. **Given** a pipeline run with 3 episodes (1 complete, 1 partial, 1 failed), **When** a `PipelineReport` is created, **Then** `episodes` contains 3 `EpisodeReport` entries with correct statuses.
2. **Given** an `EpisodeStatus` enum, **When** iterated, **Then** it contains exactly COMPLETE, PARTIAL, FAILED, SKIPPED values.

---

### Edge Cases

- What happens when a `FontAsset` has an empty `name`? Pydantic validation should reject it (minimum length 1).
- What happens when `MuxJob.fonts` is an empty list? This is valid — an episode may have no font requirements.
- What happens when `ToolResult.stderr` contains non-UTF-8 bytes? The model expects `str` — callers must decode before construction.
- What happens when `PipelineReport.episodes` is empty? This is valid — a dry-run with no episodes scanned.
- What happens when `FontAsset.layer_found` is outside 0-6 range? Pydantic validation should reject it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `FontAsset` model with fields: `name`, `file_path`, `source`, `layer_found` (constrained 0-6), `cache_hit`, `nameids`, `is_patched`, `patch_reason`
- **FR-002**: System MUST provide a `FontQuery` model with fields: `requested_name`, `anime_title`, `episode_path`
- **FR-003**: System MUST provide a `HunterResult` model with fields: `query`, `font_asset`, `success`, `hunter_name`, `duration_ms`, `attempts`
- **FR-004**: System MUST provide a `SubtitleFile` model with fields: `path`, `encoding_detected`, `encoding_source`, `line_ending`, `fonts_required`, `is_repaired`
- **FR-005**: System MUST provide a `SyncResult` model with fields: `success`, `tool_used`, `tool_fallback_used`, `offset_ms`, `duration_ms`
- **FR-006**: System MUST provide a `MuxJob` model with fields: `episode_path`, `subtitle_path`, `fonts`, `dry_run`, `output_path`
- **FR-007**: System MUST provide a `MuxResult` model with fields: `success`, `output_path`, `duration_ms`, `fonts_attached`, `warnings`
- **FR-008**: System MUST provide a `ToolResult` model with fields: `tool_name`, `success`, `exit_code`, `stdout`, `stderr`, `duration_ms`, `suggestion`
- **FR-009**: System MUST provide an `EpisodeStatus` enum with values: COMPLETE, PARTIAL, FAILED, SKIPPED
- **FR-010**: System MUST provide an `EpisodeReport` model with fields: `episode_path`, `status`, `subtitle_result`, `mux_result`, `missing_fonts`, `applied_rules`
- **FR-011**: System MUST provide a `PipelineReport` model with fields: `run_timestamp`, `duration_ms`, `anime_title`, `episodes`, `total_fonts_found`, `genuine_misses`
- **FR-012**: All models MUST use `pathlib.Path` for file path fields
- **FR-013**: All models MUST be immutable where applicable (`model_config = ConfigDict(frozen=True)`)
- **FR-014**: All models MUST have full type annotations with no use of `Any`
- **FR-015**: Models MUST have zero imports from `core/`, `adapters/`, `hunters/`, or `tui/` packages
- **FR-016**: Models MUST use Pydantic v2 (`pydantic.BaseModel`) exclusively
- **FR-017**: All models MUST be serializable to JSON and deserializable back without data loss
- **FR-018**: `FontAsset.layer_found` MUST be validated to the range 0-6
- **FR-019**: `FontAsset.name` MUST be validated to minimum length 1 (non-empty)

### Key Entities

- **FontAsset**: A resolved font file with provenance metadata (where found, which cache layer, whether patched)
- **FontQuery**: A request to find a specific font, scoped to an anime and episode
- **HunterResult**: The outcome of a single hunter's attempt to find a font
- **SubtitleFile**: A subtitle file with encoding and structural metadata
- **SyncResult**: The outcome of a subtitle synchronization operation
- **MuxJob**: A planned muxing operation with all inputs specified
- **MuxResult**: The outcome of a muxing operation
- **ToolResult**: A universal result envelope for external tool invocations
- **EpisodeStatus**: Enumeration of possible per-episode outcomes
- **EpisodeReport**: Per-episode pipeline results including fonts, subtitles, muxing
- **PipelineReport**: Aggregate pipeline results for a full run

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 11 model classes instantiate successfully with valid data and reject invalid data via Pydantic validation
- **SC-002**: All models round-trip through JSON serialization/deserialization without data loss, including `Path` fields
- **SC-003**: No model file imports from any package outside `src/models/`, standard library, or `pydantic`
- **SC-004**: 100% of model fields have explicit type annotations — no `Any` types present
- **SC-005**: All mutable-where-frozen models raise `ValidationError` on attribute assignment after construction
- **SC-006**: `FontAsset.layer_found` rejects values outside 0-6 range with a clear validation error
- **SC-007**: Models are compatible with Python 3.11+ syntax and Pydantic v2 API

## Assumptions

- Python 3.11+ is the minimum supported version per constitution
- Pydantic v2 is available as a project dependency (approved in constitution XI)
- `layer_found` range 0-6 corresponds to the font search layer hierarchy (local cache → system fonts → web sources); exact layer semantics will be defined in core logic, not in the model
- `nameids` in `FontAsset` is a dictionary mapping OpenType name ID integers to their string values (e.g., `{1: "Arial", 2: "Regular"}`)
- `applied_rules` in `EpisodeReport` is a list of strings describing which pipeline rules were triggered (e.g., "Rule 2: escalation", "Rule 3: patch")
- `encoding_source` in `SubtitleFile` represents the detection library used (e.g., "charset_normalizer", "chardet")
- Optional fields (`suggestion` in ToolResult, `tool_fallback_used` in SyncResult, `font_asset` in HunterResult, `patch_reason` in FontAsset) use `None` as default
- `MuxJob.dry_run` defaults to `False`
- Models do not enforce business logic beyond structural validation — that responsibility belongs to `src/core/`
