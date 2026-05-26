import asyncio
from pathlib import Path
import structlog
from src.models.pipeline import LibraryScanResult

logger = structlog.get_logger()


async def scan_library(library_path: Path) -> list[LibraryScanResult]:
    """Scan the library_path for MKV files and matching ASS subtitle siblings."""

    def _scan() -> list[LibraryScanResult]:
        lib_path = Path(library_path).resolve()
        results = []
        if not lib_path.exists() or not lib_path.is_dir():
            logger.warning(
                "library path does not exist or is not a directory", path=lib_path
            )
            return results

        # Find all MKV files recursively, sort them for deterministic order
        mkv_files = sorted(list(lib_path.rglob("*.mkv")), key=lambda p: p.name)

        for mkv in mkv_files:
            parent = mkv.parent
            try:
                # List sibling ASS files
                ass_files = [
                    p
                    for p in parent.iterdir()
                    if p.is_file() and p.suffix.lower() == ".ass"
                ]
            except Exception as e:
                logger.error(
                    "failed to list directory contents", directory=parent, error=str(e)
                )
                continue

            mkv_stem = mkv.stem.lower()
            matched_ass = None
            for ass in ass_files:
                if ass.stem.lower() == mkv_stem:
                    matched_ass = ass
                    break

            if matched_ass:
                anime_title = parent.name if parent.name else "Unknown"
                results.append(
                    LibraryScanResult(
                        episode_path=mkv.resolve(),
                        subtitle_path=matched_ass.resolve(),
                        anime_title=anime_title,
                    )
                )
                logger.info(
                    "discovered episode/subtitle pair",
                    episode=mkv.name,
                    subtitle=matched_ass.name,
                    anime_title=anime_title,
                )
            else:
                logger.debug("no matching ASS subtitle sibling for MKV", mkv=mkv.name)

        return results

    return await asyncio.to_thread(_scan)
