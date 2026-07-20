# Research: Pre-Packaging UX (Phase 7)

**Date**: 2026-06-06 | **Status**: Complete

## Research Tasks

### R1: QTreeWidget Tri-State Checkbox Support

**Decision**: Use `Qt.ItemFlag.ItemIsAutoTristate` flag on parent items.

**Rationale**: PySide6 `QTreeWidget` has native tri-state checkbox support. When `ItemIsAutoTristate` is set on a parent item, Qt automatically:
- Updates parent to `PartiallyChecked` when some children are checked
- Updates parent to `Checked` when all children are checked
- Updates parent to `Unchecked` when no children are checked
- Propagates parent check/uncheck to all children

No custom implementation needed. This is the recommended Qt pattern.

**Alternatives considered**:
- Manual tri-state propagation in `itemChanged` signal handler — rejected (redundant, error-prone)
- Custom QAbstractItemModel with checkboxes — rejected (overkill for 2-level tree)

### R2: Log Export Data Source

**Decision**: Read from `GuiLogBridge` session buffer (in-memory list of event dicts).

**Rationale**:
- structlog is currently configured only with `JSONRenderer()` → stdout. No file handler exists.
- Constitution §IX says "Rotating files in `.anime_studio/logs/`" but this is not yet implemented.
- `GuiLogBridge` already intercepts all INFO+ events as structured dicts.
- Adding a `list[dict]` buffer to `GuiLogBridge` is 5 lines of code.
- Reading from disk would require: setting up RotatingFileHandler, parsing JSON lines, filtering by session — much more complex.

**Alternatives considered**:
- Read from `.anime_studio/logs/` rotating files — rejected (files don't exist yet; would need to implement file logging first)
- Read from ActivityFeed's QPlainTextEdit — rejected (HTML-formatted text, lossy)

### R3: PipelineConfig selected_paths Type

**Decision**: `frozenset[SerializablePath] | None` instead of `set[Path] | None`.

**Rationale**: `PipelineConfig` uses `ConfigDict(frozen=True)`. Pydantic frozen models require immutable field types. `set` is mutable → validation error. `frozenset` is the immutable equivalent.

**Alternatives considered**:
- `tuple[Path, ...]` — works but less semantic for membership testing
- Remove `frozen=True` from PipelineConfig — rejected (breaks existing contract, constitution compliance)

### R4: _amux_ Temp File Pattern

**Decision**: Regex `^_amux_.*\.tmp\.` compiled at module level.

**Rationale**: User reported these files appear from interrupted mux operations. Pattern: `_amux_001.tmp.mkv`. The leading underscore distinguishes from legitimate files. `.tmp.` before the final extension is the marker. Compiled regex is O(1) per file check.

**Alternatives considered**:
- `fnmatch.fnmatch("_amux_*.tmp.*")` — works but regex is already imported in the module
- String `.startswith("_amux_") and ".tmp." in name` — works but less precise

### R5: MainWindow Two-Phase Run Flow

**Decision**: State machine with `_awaiting_selection: bool` flag.

**Rationale**: The Run button serves double duty:
1. First click → triggers scan → populates tree → button text stays "Run Pipeline"
2. Second click → reads selection → runs pipeline

A state flag is the simplest approach. No modal dialogs needed.

**Alternatives considered**:
- Modal dialog with tree + OK/Cancel — rejected (blocks UI, worse UX)
- Separate "Scan" and "Run" buttons — rejected (adds UI complexity, user doesn't care about scan as separate action)
- Automatic run after scan with selection widget appearing mid-flow — rejected (confusing flow)
