# Research: GUI Redesign — Two-Panel Layout

**Phase 0 Output** | **Date**: 2026-06-27

## Research Tasks

### R1: Qt Model/View Performance for Large Episode Tables

**Decision**: Use `QAbstractTableModel` + `QTableView` (not `QStandardItemModel`)

**Rationale**: `QAbstractTableModel` is memory-efficient — stores data in Python
lists, not Qt item objects. Qt MVC renders only visible rows. 500+ episodes is
trivially small for Qt's rendering pipeline.

**Alternatives considered**:
- `QStandardItemModel`: Simpler API but creates `QStandardItem` per cell → higher
  memory for large tables. Rejected.
- `QTreeView` with flat model: Unnecessary nesting complexity. Rejected.

### R2: Custom Delegate for Status Badges

**Decision**: `QStyledItemDelegate` with `paint()` override for badge rendering

**Rationale**: Lightweight — draws rounded rects + text directly via `QPainter`.
No pixmap caching needed at this scale. Consistent with Qt best practices for
custom cell rendering.

**Alternatives considered**:
- Widget delegates (`QWidget` per cell): Heavy — creates a widget instance per
  visible row. Rejected.
- HTML-rich text in model data: Limited styling control (no rounded rects, no
  background colors). Rejected.
- Pre-rendered QPixmap icons: Over-engineering for 4 solid-color badges. Rejected.

### R3: Sidebar Icon Rendering

**Decision**: Draw colored circles via `QPainter` in custom delegate (no image assets)

**Rationale**: 6 status states → 6 colors. `QPainter.drawEllipse()` with
`setBrush(QColor(...))` is 3 lines of code per icon. No asset management,
no DPI scaling issues. Colors defined as constants.

**Alternatives considered**:
- SVG icon files: Requires asset management, file loading, DPI handling.
  Over-engineering. Rejected.
- Unicode emoji: Inconsistent rendering across platforms. Rejected.
- `QIcon` from `QStyle`: Limited to system theme icons, can't customize colors. Rejected.

### R4: Cached Show Index Format

**Decision**: New file `.anime_studio/show_index.toml` (separate from `font_library.toml`)

**Rationale**: Different concern (show metadata vs font metadata), different
lifecycle (updated on Add/Remove show vs updated on font resolution), different
invalidation logic. Consistent with existing TOML usage (`config.toml`,
`font_library.toml`, `pipeline_checkpoint.toml`).

**Alternatives considered**:
- Extend `font_library.toml`: Mixes concerns, creates coupling between font
  system and GUI layout. Rejected.
- JSON file: Inconsistent with project convention (all persistent data is TOML). Rejected.
- SQLite: YAGNI — the index has at most ~100 entries. Rejected.

### R5: Scan-on-Demand Architecture

**Decision**: `LibraryScanner.scan_folder(path)` — reuses existing `_phase1_walk()`
and `_phase2_embedded_detection()` with a single-folder scope

**Rationale**: `_phase1_walk()` already accepts a `lib_path` parameter and uses
`rglob("*.mkv")` from that root. Passing a single show folder instead of the
library root naturally scopes the scan. Zero new filesystem walking logic needed.

**Alternatives considered**:
- New `ShowScanner` class: Duplicates `LibraryScanner` logic. Rejected.
- Filter results from full scan: Defeats the purpose — still scans entire library.
  Rejected.

### R6: MainWindow Rewrite Strategy

**Decision**: 3-phase migration (Build → Wire → Remove)

**Rationale**: Allows all 271 existing tests to remain passing throughout
the migration. New widgets can be tested in isolation before wiring. Old widgets
removed only after new ones are verified working.

**Alternatives considered**:
- Big-bang rewrite: All-or-nothing → all 271 tests break simultaneously. High risk.
  Rejected.
- Feature flag toggle: Over-engineering for a UI swap with no runtime switching
  requirement. Rejected.

## Resolved Clarifications

All Technical Context fields resolved — no NEEDS CLARIFICATION items.
