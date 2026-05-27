# Research: Font Ingestion System

**Feature**: 007-font-ingestion
**Date**: 2026-05-27

## 1. System Font Directory Enumeration (Cross-Platform)

**Decision**: Use `pathlib.Path` with per-OS hardcoded directories + `fonttools` for metadata extraction. No Qt imports.

**Rationale**: Constitution mandates cross-platform support (Principle II) and forbids Qt imports in non-GUI layers (Principle I). The `QFontDatabase` approach would violate hexagonal boundaries. `fonttools` is already an approved dependency for font introspection.

**OS Font Directories**:
| OS | Directories |
|----|-------------|
| Windows | `C:\Windows\Fonts`, `~\AppData\Local\Microsoft\Windows\Fonts` |
| Linux | `/usr/share/fonts/`, `/usr/local/share/fonts/`, `~/.local/share/fonts/` |
| macOS | `~/Library/Fonts/`, `/Library/Fonts/`, `/System/Library/Fonts/` |

**Discovery Pattern**:
```python
import sys
from pathlib import Path

def _get_system_font_dirs() -> list[Path]:
    if sys.platform == "win32":
        return [
            Path("C:/Windows/Fonts"),
            Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        ]
    elif sys.platform == "darwin":
        return [
            Path.home() / "Library/Fonts",
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
        ]
    else:  # Linux/BSD
        return [
            Path.home() / ".local/share/fonts",
            Path("/usr/local/share/fonts"),
            Path("/usr/share/fonts"),
        ]
```

**Index Building**: Lazily build on first `search()` call. Use `asyncio.to_thread()` to offload the blocking `fonttools` reads. Cache the index for session lifetime (no file watch — system fonts rarely change mid-session).

**Alternatives Considered**:
- `QFontDatabase`: Knows all installed fonts but lives in Qt layer. Catastrophic hexagonal violation.
- `matplotlib.font_manager`: Heavy dependency, not approved.
- `os.listdir` + filename matching: Unreliable — font filenames don't always match internal names (e.g., `comic.ttf` → "Comic Sans MS").

## 2. fonttools nameID Matching Strategy

**Decision**: Read nameID 1 (Font Family), nameID 4 (Full Name), and nameID 6 (PostScript Name) from each font file. Match the ASS `fontname` against all three, case-insensitive. First match wins.

**Rationale**: ASS subtitle files reference fonts by display name (nameID 4) most commonly, but some use the family name (nameID 1) or even PostScript name (nameID 6). Checking all three covers 99%+ of subtitle font references.

**Pattern**:
```python
from fontTools.ttLib import TTFont

def _extract_font_names(font_path: Path) -> set[str]:
    """Extract searchable font names from a font file."""
    names: set[str] = set()
    try:
        font = TTFont(font_path, fontNumber=0)
        name_table = font["name"]
        for name_id in (1, 4, 6, 16):  # family, full, postscript, typographic family
            record = name_table.getName(name_id, 3, 1, 0x0409)  # Windows, Unicode BMP, English
            if record:
                names.add(record.toUnicode().strip().lower())
            record = name_table.getName(name_id, 1, 0, 0)  # Mac, Roman, English
            if record:
                names.add(record.toUnicode().strip().lower())
        font.close()
    except Exception:
        pass  # Corrupt/unreadable font — skip
    return names
```

**Deduplication**: During ingestion, the primary name (nameID 4, falling back to nameID 1) is used as the cache key. If a font with the same primary name already exists in `FontCache`, the file is skipped.

**Alternatives Considered**:
- Filename matching: Unreliable (`arial.ttf` → "Arial", but `ARIALBI.TTF` → "Arial Bold Italic").
- SHA-256 hash: Detects identical bytes but misses same-font-different-version scenarios.
- All nameIDs: Over-matching — nameID 2 (style: "Regular", "Bold") would cause false positives.

## 3. Async Font Ingestion Strategy

**Decision**: `FontIngestionService` reads source font bytes via `asyncio.to_thread(path.read_bytes)`, extracts nameID via `fonttools`, deduplicates against `FontCache.lookup()`, then calls `FontCache.store()` for new fonts. The application-scoped disk I/O `asyncio.Semaphore` gates concurrent file reads.

**Rationale**: `FontCache.store()` already handles atomic writes (temp file → `replace()`). Reusing it avoids duplicating the write-safety logic and keeps the TOML index consistent. The semaphore is required by Constitution Principle III (Disk I/O Protection).

**Flow**:
```
For each .ttf/.otf file in source directory:
  1. Acquire disk I/O semaphore
  2. asyncio.to_thread(file.read_bytes)  →  raw bytes
  3. fonttools: extract primary name (nameID 4 → 1 fallback)
  4. FontCache.lookup(primary_name)
     ├─ HIT  → skip, increment skipped_count
     └─ MISS → FontCache.store(FontPayload(...)) → increment success_count
  5. Release semaphore
  On exception → increment failed_count, log WARNING, continue
```

**Batch Index Update**: Currently `FontCache.store()` saves the TOML index after each font. For bulk ingestion (100+ fonts), this is O(n) TOML writes. Optimization: add a `FontCache.store_batch(payloads)` method that writes the index once at the end. This is a non-breaking additive change.

**Alternatives Considered**:
- `shutil.copy2()` + separate index update: Bypasses `FontCache.store()` atomic safety. More code, less safe.
- Streaming async read/write: Over-engineered for font files (typically 50KB-5MB).
- `QThread`: Forbidden — violates hexagonal boundaries and constitution.

## 4. LibraryScanOutput Restructuring

**Decision**: Introduce `LibraryScanOutput` wrapper model containing `episodes: list[LibraryScanResult]` and `font_directories: list[Path]`. Modify `scan_library()` to return `LibraryScanOutput`.

**Rationale**: `LibraryScanResult` is per-episode (one per MKV+ASS pair). Font directories are per-library. Adding `font_directories` to each `LibraryScanResult` would wastefully duplicate the same list across all episodes. A wrapper cleanly separates the two concerns.

**Impact on PipelineRunner**: Minimal. Change `scan_results = await scan_library(...)` to:
```python
scan_output = await scan_library(pipeline_config.library_path)
scan_results = scan_output.episodes
font_dirs = scan_output.font_directories
```

**Scan Logic**: During the existing `rglob("*.mkv")` walk, also detect `Fonts/` and `fonts/` directories. Since `rglob` only finds files, add a separate check: `library_path.rglob("*")` filtered to directories matching `fonts` (case-insensitive). Deduplicate by resolved path.

**Optimization**: Use a single `os.walk()` (via `asyncio.to_thread()`) instead of two `rglob()` calls. Collect both MKV paths and font directories in one pass.

**Alternatives Considered**:
- Return `tuple[list[LibraryScanResult], list[Path]]`: Less structured, harder to extend.
- Add to each `LibraryScanResult`: Wasteful duplication (same list × N episodes).
- Separate `scan_font_directories()` function: Extra directory walk.

## 5. FontResolver Modification for is_cacheable

**Decision**: Add a 3-line check in `FontResolver.resolve()` after `hunter.search()` returns. If the first `HunterResult` contains a `FontAsset` with `is_cacheable=False`, return it directly — skip `download()` and `cache.store()`.

**Rationale**: `SystemFontHunter` resolves fonts in-place (absolute path to system font). There's no "download" step and no reason to copy into cache. The hunter's `search()` method returns a fully-populated `FontAsset` directly in the `HunterResult.font_asset` field.

**Code Change** (in `font_resolver.py` L60-68, inside the hunter iteration loop):
```python
results = await hunter.search(query)
if results and results[0].success:
    # System fonts resolve in-place — skip download and cache
    if results[0].font_asset and not results[0].font_asset.is_cacheable:
        cb.record_success()
        return results[0].font_asset
    # Network/other hunters — download and cache
    payload = await hunter.download(results[0])
    asset = self.cache.store(payload, layer_found=hunter.priority)
```

**SystemFontHunter.download()**: Must exist to satisfy `HunterProtocol` but should raise `NotImplementedError` — it should never be called when the resolver correctly checks `is_cacheable`.

**Alternatives Considered**:
- Skip based on hunter type name: Fragile string matching, violates OCP.
- Add `is_local` flag to HunterProtocol: Protocol change affects all hunters. `is_cacheable` on FontAsset is more granular and already decided during /grill-me.

## 6. PySide6 Drag & Drop Implementation

**Decision**: `setAcceptDrops(True)` on `MainWindow`. Override `dragEnterEvent()` for MIME validation and visual feedback. Override `dropEvent()` to trigger async ingestion via `@asyncSlot()`.

**Rationale**: Qt's drag-drop system uses event overrides on the target widget. The MainWindow is the broadest target — easy to hit, discoverable. MIME type filtering (`hasUrls()` + extension check) prevents accidental ingestion of non-font items.

**Pattern**:
```python
class MainWindow(QMainWindow):
    def __init__(self, ...):
        super().__init__()
        self.setAcceptDrops(True)
        self._default_style = self.styleSheet()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(self._is_font_drop(url) for url in urls):
                event.acceptProposedAction()
                self.setStyleSheet("QMainWindow { border: 3px solid #4CAF50; }")
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._default_style)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self._default_style)
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        asyncio.ensure_future(self._handle_font_drop(paths))

    def _is_font_drop(self, url) -> bool:
        path = Path(url.toLocalFile())
        if path.is_dir():
            return True
        return path.suffix.lower() in ('.ttf', '.otf')
```

**Visual Feedback**: Green border highlight during valid drag-over. Reset on `dragLeaveEvent` and `dropEvent`. Uses `setStyleSheet()` with a solid border — minimal, non-intrusive, clearly visible on dark theme.

**Alternatives Considered**:
- Overlay widget: More complex, requires z-ordering management.
- Dedicated drop zone: Smaller target, less discoverable.
- `QDrag` custom MIME: Over-engineered for filesystem drops.

## 7. Application-Scoped Disk I/O Semaphore

**Decision**: Create a single `asyncio.Semaphore(config.max_concurrent_disk_io)` in `bootstrap_app()` and inject it into both `PipelineRunner` and `FontIngestionService`. `PipelineRunner` stops creating per-run semaphores.

**Rationale**: Constitution Principle III mandates "application-scoped (singleton lifetime) and injected into adapters via constructor or config, never created per-call." Currently, `PipelineRunner.run()` creates a new semaphore per run (L100) — this is a pre-existing deviation that should be fixed.

**Impact**:
1. `PipelineRunner.__init__` gains `disk_semaphore: asyncio.Semaphore` parameter.
2. `PipelineRunner.run()` uses `self.disk_semaphore` instead of creating new one.
3. `FontIngestionService.__init__` takes `disk_semaphore: asyncio.Semaphore`.
4. `bootstrap_app()` creates the semaphore and passes to both.

**Alternatives Considered**:
- Separate semaphores per service: Doesn't bound total concurrent I/O when pipeline + import run simultaneously.
- Global module-level semaphore: Forbidden (global mutable state).
- Config-based lazy creation: Extra complexity, still needs singleton management.
