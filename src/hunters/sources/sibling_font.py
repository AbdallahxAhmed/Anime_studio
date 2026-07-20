import asyncio
import time
from pathlib import Path
import structlog

from src.models.font import FontQuery, FontAsset, HunterResult, FontPayload
from src.hunters.sources._hunter_utils import (
    verify_font,
    font_name_matches,
    FONT_EXTENSIONS,
)

logger = structlog.get_logger()


def _scan_directories_sync(
    candidate_dirs: list[Path], requested_name: str
) -> tuple[Path, str, dict[int, str]] | None:
    """Synchronously scan directories for matching fonts. To be run in a separate thread."""
    for fonts_dir in candidate_dirs:
        logger.debug("Scanning sibling directory", path=str(fonts_dir))
        if not fonts_dir.is_dir():
            continue
        try:
            for p in fonts_dir.iterdir():
                if p.is_file() and p.suffix.lower() in FONT_EXTENSIONS:
                    try:
                        data = p.read_bytes()
                        nameids = verify_font(data, p.name)
                        if nameids and font_name_matches(requested_name, nameids):
                            # Determine primary name
                            primary_name = nameids.get(4) or nameids.get(1) or p.stem
                            return p, primary_name, nameids
                    except Exception as e:
                        logger.debug(
                            "Failed to process font candidate",
                            path=str(p),
                            error=str(e),
                        )
        except Exception as e:
            logger.debug("Error iterating directory", path=str(fonts_dir), error=str(e))
    return None


class SiblingFontHunter:
    name: str = "SiblingFontHunter"
    priority: int = 2
    rate_limit: float = 0.0
    circuit_breaker_threshold: int = 3
    ping_url: str | None = None

    def supports(self, query: FontQuery) -> bool:
        return True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        logger.debug("SiblingFontHunter search start", requested=query.requested_name)
        if not query.episode_path:
            return []

        start_time = time.perf_counter()
        episode_dir = Path(query.episode_path).parent

        # Construct candidate directories in priority order
        candidate_dirs = []
        for dir_name in ("Fonts", "fonts", "Font", "font"):
            candidate_dirs.append(episode_dir / dir_name)

        if episode_dir.parent != episode_dir:
            for dir_name in ("Fonts", "fonts"):
                candidate_dirs.append(episode_dir.parent / dir_name)

        # Offload file I/O and verification to a thread pool
        match_info = await asyncio.to_thread(
            _scan_directories_sync, candidate_dirs, query.requested_name
        )

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        if match_info:
            path, primary_name, nameids = match_info
            logger.info(
                "Sibling font match found",
                requested_name=query.requested_name,
                matched_name=primary_name,
                path=str(path),
            )
            asset = FontAsset(
                name=primary_name,
                file_path=path,
                source="sibling",
                layer_found=self.priority,
                cache_hit=False,
                nameids=nameids,
                is_cacheable=True,
            )
            return [
                HunterResult(
                    query=query,
                    font_asset=asset,
                    success=True,
                    hunter_name=self.name,
                    duration_ms=duration_ms,
                    attempts=1,
                )
            ]

        logger.debug("Sibling font miss", requested_name=query.requested_name)
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        if not result.font_asset or not result.font_asset.file_path:
            raise ValueError("Invalid result for download")

        path = Path(result.font_asset.file_path)
        font_bytes = await asyncio.to_thread(path.read_bytes)

        return FontPayload(
            font_name=result.font_asset.name,
            font_data=font_bytes,
            file_extension=path.suffix.lower(),
            source=self.name,
            nameids=result.font_asset.nameids,
            metadata={},
        )
