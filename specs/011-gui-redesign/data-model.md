# Data Model: GUI Redesign — Two-Panel Layout

**Phase 1 Output** | **Date**: 2026-06-27

## New Entities

### ShowStatus (Enum)

```
ShowStatus : StrEnum
├── PENDING       = "pending"         # Not yet scanned
├── PROCESSING    = "processing"      # Scan in progress
├── READY         = "ready"           # Scanned, episodes available
├── ALL_DONE      = "all_done"        # All episodes muxed
├── NO_SUBTITLE   = "no_subtitle"     # MKVs exist but no ASS files
└── WARNING       = "warning"         # Errors occurred
```

**Location**: `src/models/pipeline.py`
**Type**: `StrEnum` (Python 3.11+)
**Serialization**: String value directly in TOML

### ShowSummary (Frozen Dataclass)

```
ShowSummary : @dataclass(frozen=True)
├── name: str                    # Show display name (directory name)
├── path: Path                   # Absolute path to show folder
├── status: ShowStatus           # Current status for sidebar icon
├── episode_count: int           # Total episodes detected
├── processed_count: int         # Episodes already muxed
└── subtitle_text: str           # Display string: "12 ready / 2 processed"
```

**Location**: `src/models/pipeline.py`
**Frozen**: Yes (immutable after creation)
**I/O**: Zero — pure data container

### Relationships

```
ShowSummary
  ├── status → ShowStatus (enum value)
  ├── path → maps to LibraryScanResult.episode_path.parent
  └── one-to-many → LibraryScanResult (via scan_folder)

ShowIndexManager
  ├── persists list[ShowSummary] → show_index.toml
  └── loads list[ShowSummary] ← show_index.toml

ShowSidebarWidget
  ├── renders list[ShowSummary]
  └── emits show_selected → triggers scan_folder() → LibraryScanOutput

EpisodeTableWidget
  ├── renders list[LibraryScanResult]
  └── emits selection_changed → list[Path] for pipeline
```

## Existing Entities (Unchanged)

### LibraryScanResult (Pydantic, frozen)
Used by `EpisodeTableWidget.populate()`. Fields: `episode_path`, `subtitle_path`,
`subtitle_source`, `anime_title`, `embedded_sub_info`.

### LibraryScanOutput (Pydantic, frozen)
Returned by `scan_folder()`. Fields: `episodes`, `font_directories`, `show_tree`.

### PipelineConfig (Pydantic, frozen)
Used by `_on_run_selected()`. Fields: `library_path`, `dry_run`, `sync_enabled`,
`anime_title`, `selected_paths`.

## State Transitions

### ShowStatus Lifecycle

```
PENDING → PROCESSING → READY
                     → NO_SUBTITLE
                     → WARNING

READY → PROCESSING → ALL_DONE
                   → WARNING

ALL_DONE → PROCESSING → READY  (if new episodes added)
```

## TOML Schema: show_index.toml

```toml
# .anime_studio/show_index.toml
# Cached show index for instant sidebar population

[[shows]]
name = "Hunter x Hunter"
path = "D:/Anime/Hunter x Hunter"
episode_count = 148
processed_count = 0
status = "ready"
subtitle_text = "148 ready / 0 processed"

[[shows]]
name = "Vinland Saga"
path = "D:/Anime/Vinland Saga"
episode_count = 24
processed_count = 24
status = "all_done"
subtitle_text = "24 processed"
```

## Validation Rules

| Entity | Field | Rule |
|--------|-------|------|
| ShowSummary | name | Non-empty string |
| ShowSummary | path | Must be absolute `Path` |
| ShowSummary | episode_count | >= 0 |
| ShowSummary | processed_count | >= 0, <= episode_count |
| ShowStatus | value | Must be one of 6 enum values |
| show_index.toml | schema | Array of tables `[[shows]]` |
