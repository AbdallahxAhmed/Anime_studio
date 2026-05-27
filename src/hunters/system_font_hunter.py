import asyncio
import sys
import time
from pathlib import Path
from fontTools.ttLib import TTFont
import structlog

from src.models.font import FontQuery, FontAsset, HunterResult, FontPayload

logger = structlog.get_logger()


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


def _extract_font_names(font_path: Path) -> tuple[str, dict[int, str], set[str]]:
    """
    Extract searchable font names and all nameids from a font file.
    Returns: (primary_name, nameids_dict, searchable_names_set)
    """
    searchable_names: set[str] = set()
    nameids: dict[int, str] = {}
    primary_name = font_path.stem

    try:
        font = TTFont(font_path, fontNumber=0)
        name_table = font["name"]

        for name_id in (1, 4, 6, 16):
            # Windows, Unicode BMP, English
            record = name_table.getName(name_id, 3, 1, 0x0409)
            if record:
                val = record.toUnicode().strip()
                nameids[name_id] = val
                searchable_names.add(val.lower())

            # Mac, Roman, English
            record = name_table.getName(name_id, 1, 0, 0)
            if record:
                val = record.toUnicode().strip()
                nameids[name_id] = val
                searchable_names.add(val.lower())

        font.close()

        if 4 in nameids:
            primary_name = nameids[4]
        elif 1 in nameids:
            primary_name = nameids[1]

    except Exception as e:
        logger.debug("Failed to extract font names", path=str(font_path), error=str(e))

    return primary_name, nameids, searchable_names


class SystemFontHunter:
    name: str = "SystemFontHunter"
    priority: int = 4
    rate_limit: float = 0.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = None

    def __init__(self):
        self._index: dict[str, tuple[Path, str, dict[int, str]]] = {}
        self._index_built: bool = False

    def supports(self, query: FontQuery) -> bool:
        return True

    def _build_index(self) -> None:
        """Scan system directories and index all valid fonts."""
        if self._index_built:
            return

        logger.info("Building system font index...")
        start_time = time.perf_counter()

        dirs = _get_system_font_dirs()
        indexed_count = 0

        for d in dirs:
            if not d.exists():
                logger.debug("System font directory does not exist", path=str(d))
                continue

            try:
                for p in d.rglob("*"):
                    if p.is_file() and p.suffix.lower() in (".ttf", ".otf"):
                        primary_name, nameids, searchable_names = _extract_font_names(p)
                        if not searchable_names:
                            continue

                        for s_name in searchable_names:
                            if s_name not in self._index:
                                self._index[s_name] = (p, primary_name, nameids)
                        indexed_count += 1
            except Exception as e:
                logger.warning(
                    "Error scanning system font directory",
                    path=str(d),
                    error=str(e),
                )

        duration = time.perf_counter() - start_time
        logger.info(
            "System font index built",
            indexed_fonts=indexed_count,
            duration_s=duration,
        )
        self._index_built = True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        """Search system fonts for a match (case-insensitive)."""
        if not self._index_built:
            await asyncio.to_thread(self._build_index)

        requested = query.requested_name.strip().lower()

        start_time = time.perf_counter()

        if requested in self._index:
            path, primary_name, nameids = self._index[requested]
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            asset = FontAsset(
                name=primary_name,
                file_path=path,
                source="system",
                layer_found=self.priority,
                cache_hit=False,
                nameids=nameids,
                is_cacheable=False,
            )

            result = HunterResult(
                query=query,
                font_asset=asset,
                success=True,
                hunter_name=self.name,
                duration_ms=duration_ms,
                attempts=1,
            )
            logger.info(
                "System font match found",
                requested_name=query.requested_name,
                matched_name=primary_name,
                path=str(path),
            )
            return [result]

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info("System font miss", requested_name=query.requested_name)
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        raise NotImplementedError(
            "SystemFontHunter resolves fonts in-place; download is not supported."
        )
