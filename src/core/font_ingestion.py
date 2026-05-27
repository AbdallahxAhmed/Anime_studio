import asyncio
from io import BytesIO
from pathlib import Path
from fontTools.ttLib import TTFont  # type: ignore[import-untyped]
import structlog

from src.models.font import FontPayload
from src.models.ingestion import FontIngestionResult
from src.core.font_cache import FontCache

logger = structlog.get_logger()


def _extract_font_name_from_bytes(
    data: bytes, file_stem: str
) -> tuple[str, dict[int, str]]:
    nameids = {}
    primary_name = file_stem
    try:
        font = TTFont(BytesIO(data), fontNumber=0)
        name_table = font["name"]
        for name_id in (1, 4, 6, 16):
            record = name_table.getName(name_id, 3, 1, 0x0409)
            if record:
                nameids[name_id] = record.toUnicode().strip()
            record = name_table.getName(name_id, 1, 0, 0)
            if record:
                nameids[name_id] = record.toUnicode().strip()
        font.close()

        # Deduplication MUST use nameID 4 (full name), falling back to nameID 1 (family name)
        if 4 in nameids:
            primary_name = nameids[4]
        elif 1 in nameids:
            primary_name = nameids[1]
    except Exception as e:
        raise ValueError(f"Failed to parse font metadata: {e}")
    return primary_name, nameids


class FontIngestionService:
    """Async service orchestrating discovery, deduplication, and caching of fonts."""

    def __init__(self, cache: FontCache, disk_semaphore: asyncio.Semaphore):
        self.cache = cache
        self.disk_semaphore = disk_semaphore

    async def ingest_directories(
        self, directories: list[Path], source: str = "manual_import"
    ) -> FontIngestionResult:
        """Scan directories recursively and ingest all discovered font files."""
        files_to_ingest = []
        for d in directories:
            d_path = Path(d).resolve()
            if not d_path.exists() or not d_path.is_dir():
                logger.warning(
                    "Ingestion directory does not exist or is not a directory",
                    path=str(d_path),
                )
                continue

            def _find_fonts(dir_path: Path) -> list[Path]:
                found = []
                for p in dir_path.rglob("*"):
                    if p.is_file() and p.suffix.lower() in (".ttf", ".otf"):
                        found.append(p)
                return found

            found_files = await asyncio.to_thread(_find_fonts, d_path)
            files_to_ingest.extend(found_files)

        return await self.ingest_files(files_to_ingest, source=source)

    async def ingest_files(
        self, files: list[Path], source: str = "manual_import"
    ) -> FontIngestionResult:
        """Ingest specific individual font files with deduplication and validation."""
        success_count = 0
        skipped_count = 0
        failed_count = 0
        failed_details: list[tuple[Path, str]] = []

        unique_files = list(dict.fromkeys(files))

        async def _ingest_single_file(f: Path) -> tuple[str, Path, str | None]:
            try:
                if not f.is_file():
                    return "failed", f, "Not a file or file does not exist"

                async with self.disk_semaphore:
                    data = await asyncio.to_thread(f.read_bytes)
                    primary_name, nameids = await asyncio.to_thread(
                        _extract_font_name_from_bytes, data, f.stem
                    )

                    cached = self.cache.lookup(primary_name)
                    if cached is not None:
                        return "skipped", f, None

                    payload = FontPayload(
                        font_name=primary_name,
                        font_data=data,
                        file_extension=f.suffix.lstrip("."),
                        source=source,
                        nameids=nameids,
                        metadata={},
                    )

                    await asyncio.to_thread(self.cache.store, payload, 0)

                return "success", f, None
            except Exception as e:
                return "failed", f, str(e)

        tasks = [_ingest_single_file(f) for f in unique_files]
        results = await asyncio.gather(*tasks)

        for status, f, error_reason in results:
            if status == "success":
                success_count += 1
            elif status == "skipped":
                skipped_count += 1
            else:
                failed_count += 1
                failed_details.append((f, error_reason or "Unknown error"))
                logger.warning(
                    "Font ingestion failed for file",
                    path=str(f),
                    error=error_reason,
                )

        logger.info(
            "font_ingestion_complete",
            success_count=success_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            source=source,
        )

        return FontIngestionResult(
            success_count=success_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            failed_details=failed_details,
            source=source,
        )
