# Data Model: Font Ingestion System

**Feature**: 007-font-ingestion
**Date**: 2026-05-27

## Entities

### Modified Entities

#### FontAsset (`src/models/font.py`)

Add `is_cacheable` field to support system font resolve-in-place:

| Field | Type | Default | Change |
|-------|------|---------|--------|
| `name` | `str` | — | existing |
| `file_path` | `SerializablePath` | — | existing |
| `source` | `str` | — | existing |
| `layer_found` | `int` | — | existing (0-6) |
| `cache_hit` | `bool` | — | existing |
| `nameids` | `dict[int, str]` | — | existing |
| `is_patched` | `bool` | `False` | existing |
| `patch_reason` | `str \| None` | `None` | existing |
| **`is_cacheable`** | **`bool`** | **`True`** | **NEW** |

When `is_cacheable=False`, the pipeline skips `FontCache.store()` and uses the absolute path directly. Only `SystemFontHunter` sets this to `False`.

#### LibraryScanResult → LibraryScanOutput (`src/models/pipeline.py`)

Wrap existing `LibraryScanResult` in a new output model:

**Existing `LibraryScanResult`** (unchanged):
| Field | Type |
|-------|------|
| `episode_path` | `SerializablePath` |
| `subtitle_path` | `SerializablePath` |
| `anime_title` | `str` |

**New `LibraryScanOutput`**:
| Field | Type | Default |
|-------|------|---------|
| `episodes` | `list[LibraryScanResult]` | — |
| `font_directories` | `list[SerializablePath]` | `[]` |

`scan_library()` return type changes from `list[LibraryScanResult]` → `LibraryScanOutput`.

### New Entities

#### FontIngestionResult (`src/models/ingestion.py`)

Value object returned by all ingestion operations:

| Field | Type | Purpose |
|-------|------|---------|
| `success_count` | `int` | Fonts successfully copied to cache |
| `skipped_count` | `int` | Fonts skipped (already in cache by name) |
| `failed_count` | `int` | Fonts that failed (corrupt, permission error) |
| `failed_details` | `list[tuple[SerializablePath, str]]` | (path, error message) for each failure |
| `source` | `str` | Origin: `"auto_discovery"`, `"manual_import"`, or `"drag_drop"` |

Frozen Pydantic `BaseModel` with `ConfigDict(frozen=True)`.

### New Services

#### FontIngestionService (`src/core/font_ingestion.py`)

Stateless async service. Core layer — no Qt/GUI imports.

**Constructor dependencies** (injected):
| Dependency | Type | Purpose |
|------------|------|---------|
| `cache` | `FontCache` | Lookup for dedup, store for new fonts |
| `disk_semaphore` | `asyncio.Semaphore` | Bound concurrent disk I/O |

**Public methods**:
| Method | Signature | Purpose |
|--------|-----------|---------|
| `ingest_directories` | `async (dirs: list[Path], source: str) -> FontIngestionResult` | Scan dirs for .ttf/.otf, dedup, ingest |
| `ingest_files` | `async (files: list[Path], source: str) -> FontIngestionResult` | Ingest specific font files |

#### SystemFontHunter (`src/hunters/system_font_hunter.py`)

`HunterProtocol` implementation for OS font resolution.

**Attributes**:
| Attribute | Value | Rationale |
|-----------|-------|-----------|
| `name` | `"system_fonts"` | Descriptive identifier |
| `priority` | `4` | Layer 4: between sibling scan (3) and network (5) |
| `rate_limit` | `0.0` | Local I/O, no throttling needed |
| `circuit_breaker_threshold` | `3` | Default; trips on repeated OS access errors |
| `ping_url` | `None` | No network; startup_ping skips it |

**Behavior**:
- `supports(query)`: Always `True` — any font could be a system font.
- `search(query)`: Lazily builds name→path index on first call via `fonttools`. Matches `query.requested_name` case-insensitively. Returns `HunterResult` with `FontAsset(is_cacheable=False, source="system", file_path=<absolute_path>)`.
- `download(result)`: Raises `NotImplementedError` — never called when `is_cacheable=False`.

## Relationships

```
MainWindow (GUI)
    ├── "Import Fonts" button ──→ QFileDialog ──→ asyncSlot ──→ FontIngestionService.ingest_directories()
    ├── Drop event ──→ asyncSlot ──→ FontIngestionService.ingest_files() / ingest_directories()
    └── SignalBridge.log_received ←── structlog ←── FontIngestionService (logs results)

PipelineRunner (Core)
    ├── scan_library() ──→ LibraryScanOutput (episodes + font_directories)
    ├── FontIngestionService.ingest_directories(font_dirs) ──→ pre-pipeline step
    └── FontResolver.resolve(query) ──→ HunterRegistry.iter_hunters()
                                            ├── SystemFontHunter.search(query) ──→ FontAsset(is_cacheable=False)
                                            │   └── [resolver skips download+store]
                                            └── [other hunters] ──→ download ──→ cache.store

FontIngestionService (Core)
    ├── reads bytes ──→ asyncio.to_thread(path.read_bytes)
    ├── parses names ──→ fonttools (nameID 1, 4)
    ├── dedup check ──→ FontCache.lookup(name)
    └── stores new ──→ FontCache.store(FontPayload)

bootstrap_app() (DI Assembly)
    ├── asyncio.Semaphore(config.max_concurrent_disk_io) ──→ [shared singleton]
    ├── FontIngestionService(cache, disk_semaphore)
    ├── PipelineRunner(font_resolver, ..., disk_semaphore)
    └── MainWindow(pipeline_runner, font_ingestion_service, log_bridge, config)
```

## State Transitions

### Font Ingestion Flow

```
IDLE ──[trigger]──→ SCANNING_SOURCE
  triggers: Import button, drag-drop, auto-discovery

SCANNING_SOURCE ──[found files]──→ PROCESSING
  action: enumerate .ttf/.otf files in source directories

PROCESSING ──[per file]──→ DEDUP_CHECK
  action: read bytes, extract nameID via fonttools

DEDUP_CHECK
  ├─ [name in cache] ──→ SKIPPED (increment skipped_count)
  └─ [name not in cache] ──→ STORING
       action: FontCache.store(payload)
       └─ [success] ──→ STORED (increment success_count)
       └─ [failure] ──→ FAILED (increment failed_count, log WARNING)

All files processed ──→ COMPLETE
  action: log FontIngestionResult via structlog
  signal: SignalBridge.log_received ──→ ActivityFeedWidget
```
