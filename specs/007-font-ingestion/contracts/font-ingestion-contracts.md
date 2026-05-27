# Contracts: Font Ingestion System

**Feature**: 007-font-ingestion
**Date**: 2026-05-27

## 1. FontIngestionService Contract

**Layer**: Core (`src/core/font_ingestion.py`)
**Type**: Application Service (Use Case)
**Dependencies**: `FontCache`, `asyncio.Semaphore` (injected)

### Interface

```python
class FontIngestionService:
    """Async service for ingesting font files into the permanent cache.

    Stateless. No GUI/Qt imports. All I/O via asyncio.to_thread().
    Deduplicates by internal font name (fonttools nameID 1/4).
    """

    def __init__(self, cache: FontCache, disk_semaphore: asyncio.Semaphore) -> None: ...

    async def ingest_directories(
        self,
        directories: list[Path],
        source: str = "auto_discovery",
    ) -> FontIngestionResult:
        """Scan directories for .ttf/.otf files and ingest new fonts into cache.

        Args:
            directories: List of directory paths to scan (recursive).
            source: Origin label for reporting ("auto_discovery", "manual_import", "drag_drop").

        Returns:
            FontIngestionResult with counts of success/skipped/failed.

        Notes:
            - Directories are scanned recursively for .ttf and .otf files.
            - Deduplication by internal font name (fonttools nameID).
            - Each file read is gated by the disk I/O semaphore.
            - Corrupt/unreadable fonts are logged at WARNING and counted as failed.
            - The FontCache TOML index is updated atomically after the batch.
        """
        ...

    async def ingest_files(
        self,
        files: list[Path],
        source: str = "drag_drop",
    ) -> FontIngestionResult:
        """Ingest specific font files into cache.

        Args:
            files: List of .ttf/.otf file paths.
            source: Origin label for reporting.

        Returns:
            FontIngestionResult with counts.
        """
        ...
```

### Invariants

- MUST NOT import from `src/gui/`, `PySide6`, or any UI framework.
- MUST use `asyncio.to_thread()` for all blocking file reads.
- MUST acquire `disk_semaphore` before each file read.
- MUST use `FontCache.lookup()` for dedup and `FontCache.store()` for writes.
- MUST log `font_ingestion_complete` event via `structlog` with `success_count`, `skipped_count`, `failed_count`, `source` fields.
- MUST NOT raise exceptions for individual file failures — aggregate into `failed_count`.
- MUST return `FontIngestionResult` even if all files fail (0 success, 0 skipped, N failed).

---

## 2. SystemFontHunter Contract

**Layer**: Hunters (`src/hunters/system_font_hunter.py`)
**Type**: `HunterProtocol` implementation (Driven Adapter)
**Dependencies**: None (pure, stateless after index build)

### Interface

```python
class SystemFontHunter:
    """HunterProtocol implementation for cross-platform OS font discovery.

    Scans standard OS font directories, builds a name→path index via fonttools,
    and resolves fonts in-place (no copying). Returns FontAsset with is_cacheable=False.
    """

    name: str = "system_fonts"
    priority: int = 4
    rate_limit: float = 0.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = None

    def supports(self, query: FontQuery) -> bool:
        """Always True — any font could be a system font."""
        ...

    async def search(self, query: FontQuery) -> list[HunterResult]:
        """Search OS font directories for the requested font.

        On first call, lazily builds the name→path index by scanning all
        OS font directories via fonttools (asyncio.to_thread).
        Matches query.requested_name case-insensitively against nameID 1, 4, 6, 16.

        Returns:
            - [HunterResult(success=True, font_asset=FontAsset(is_cacheable=False))] on match
            - [] on no match
        """
        ...

    async def download(self, result: HunterResult) -> FontPayload:
        """Not supported — system fonts are resolved in-place.

        Raises:
            NotImplementedError: Always. FontResolver skips this when is_cacheable=False.
        """
        ...
```

### Invariants

- MUST conform to `HunterProtocol` (runtime_checkable).
- MUST NOT import from `src/gui/`, `PySide6`, or `httpx`.
- MUST use `pathlib.Path` for all path operations (Constitution Principle II).
- MUST detect OS via `sys.platform` and scan appropriate directories.
- MUST use `fonttools` (`TTFont`) for nameID extraction — never match by filename.
- `FontAsset` returned MUST have `is_cacheable=False` and `source="system"`.
- Index build MUST use `asyncio.to_thread()` to avoid blocking the event loop.
- MUST handle inaccessible directories gracefully (log WARNING, skip, continue).

---

## 3. FontResolver Contract Addendum

**Change**: `resolve()` method gains a short-circuit for non-cacheable assets.

### Modified Behavior

```python
# After hunter.search() returns results:
if results and results[0].success:
    # Short-circuit: system fonts already resolved in-place
    if results[0].font_asset and not results[0].font_asset.is_cacheable:
        cb.record_success()
        return results[0].font_asset
    # Standard path: download and cache
    payload = await hunter.download(results[0])
    asset = self.cache.store(payload, layer_found=hunter.priority)
```

### Invariants

- MUST check `is_cacheable` before calling `download()` and `store()`.
- MUST record success on circuit breaker for non-cacheable resolutions.
- MUST NOT alter behavior for cacheable fonts (backward compatible).

---

## 4. MainWindow UI Contract Addendum

**Change**: Add "Import Fonts" button and drag-drop support.

### Import Button

- **Position**: Left panel config group, between `LibraryPickerWidget` and "Run Pipeline" button.
- **Label**: `"Import Fonts"`
- **Behavior**: Opens `QFileDialog.getExistingDirectory()`. On selection, calls `FontIngestionService.ingest_directories()` via `@asyncSlot()`.
- **Feedback**: Result emitted as structlog event → `SignalBridge.log_received` → `ActivityFeedWidget`.

### Drag & Drop

- **Target**: Entire `MainWindow` (`setAcceptDrops(True)`).
- **Valid drops**: Folders or files with `.ttf`/`.otf` extension.
- **Visual feedback**: Green border (`3px solid #4CAF50`) on valid `dragEnterEvent`. Reset on `dragLeaveEvent`/`dropEvent`.
- **Behavior**: Folders → `ingest_directories()`. Individual files → `ingest_files()`. Both via `@asyncSlot()`.

### Invariants

- MUST NOT contain ingestion logic — delegate entirely to `FontIngestionService`.
- MUST NOT block the Qt event loop — all ingestion via `qasync` async tasks.
- MUST validate MIME data in `dragEnterEvent` before accepting.
