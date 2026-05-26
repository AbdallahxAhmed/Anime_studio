# Research: Domain Models Layer

**Feature**: 001-domain-models | **Date**: 2026-05-18

## R-001: Pydantic v2 Frozen Models

**Decision**: Use `model_config = ConfigDict(frozen=True)` on all domain models.

**Rationale**: Constitution mandates immutability (FR-013). Pydantic v2 `frozen=True` raises `ValidationError` on attribute assignment after construction. No performance penalty — Pydantic's Rust core handles it natively.

**Alternatives considered**:
- `@dataclass(frozen=True)` — rejected: loses Pydantic validation, JSON Schema export, and `model_dump_json()` round-trip
- `NamedTuple` — rejected: no field validators, no JSON serialization, awkward nested models

## R-002: Path Serialization Strategy

**Decision**: Use `Annotated[Path, PlainSerializer(lambda p: p.as_posix(), return_type=str)]` type alias (`PosixPath`) for all `Path` fields.

**Rationale**: Spec acceptance scenario requires Path fields serialize as POSIX strings and deserialize back to `Path` objects. Pydantic v2 natively coerces strings → `Path` on `model_validate_json()`. Using `.as_posix()` ensures cross-platform consistency (Windows `\` → `/` in JSON).

**Alternatives considered**:
- `@field_serializer` per-model — rejected: repetitive, violates DRY when 6+ models have Path fields
- Default `str(path)` — rejected: produces `\\` on Windows, breaks cross-platform JSON portability
- No custom serializer — rejected: default `str()` uses OS-native separators

## R-003: Enum Strategy for EpisodeStatus

**Decision**: Use `enum.StrEnum` (Python 3.11+).

**Rationale**: Constitution requires Python 3.11+. `StrEnum` values serialize directly to JSON strings without custom serializers. Pydantic v2 handles `StrEnum` natively.

**Alternatives considered**:
- `enum.Enum` with string values — rejected: requires `.value` access everywhere, worse DX
- Literal types — rejected: no iteration support needed by FR-009 acceptance scenario

## R-004: Model Module Organization

**Decision**: Split models across 4 files matching domain boundaries:
- `font.py` — `FontAsset`, `FontQuery`, `HunterResult`
- `subtitle.py` — `SubtitleFile`, `SyncResult`
- `mux.py` — `MuxJob`, `MuxResult`
- `tool_result.py` — `ToolResult`
- `report.py` — `EpisodeStatus`, `EpisodeReport`, `PipelineReport`
- `_types.py` — shared type aliases (`PosixPath`)

Re-export all models from `src/models/__init__.py`.

**Rationale**: Constitution §XII (Flat Over Nested) — each file has 1-3 related models. Constitution file organization shows this exact structure. Shared `_types.py` for `PosixPath` alias avoids circular imports.

**Alternatives considered**:
- Single `models.py` file — rejected: 11 models + imports would exceed 300 lines, harder to navigate
- One file per model — rejected: 11 files for small models is excessive (Constitution §XII YAGNI)

## R-005: Validation Constraints

**Decision**: Use Pydantic v2 `Field()` with `ge=0, le=6` for `layer_found`, `min_length=1` for `FontAsset.name`.

**Rationale**: Direct mapping from FR-018 and FR-019. Pydantic v2 `Field` constraints generate clear `ValidationError` messages automatically.

**Alternatives considered**:
- `@field_validator` — rejected: overkill for simple range/length checks that `Field()` handles
- Custom `__init__` validation — rejected: anti-pattern in Pydantic, loses declarative schema

## R-006: `nameids` Field Type

**Decision**: `dict[int, str]` for `FontAsset.nameids`.

**Rationale**: Spec assumption states "mapping OpenType name ID integers to their string values (e.g., `{1: 'Arial', 2: 'Regular'}`)". `dict[int, str]` is the natural Pydantic type. JSON serializes keys as strings, Pydantic v2 coerces string keys → int on deserialization.

**Alternatives considered**:
- `dict[str, str]` — rejected: loses semantic meaning, OpenType name IDs are integers
- Custom `NameId` model — rejected: YAGNI, simple dict sufficient
