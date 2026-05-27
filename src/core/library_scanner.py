import asyncio
from pathlib import Path
import structlog
from src.models.pipeline import LibraryScanResult, LibraryScanOutput

logger = structlog.get_logger()


def _is_excluded(path: Path, base: Path) -> bool:
    """Return True if any path component relative to base starts with '.'."""
    try:
        relative = path.relative_to(base)
    except ValueError:
        return False
    return any(part.startswith(".") for part in relative.parts)


async def scan_library(library_path: Path) -> LibraryScanOutput:
    """Scan the library_path for MKV files, matching ASS subtitle siblings, and Fonts directories."""

    def _scan() -> LibraryScanOutput:
        lib_path = Path(library_path).resolve()
        results = []
        font_dirs = set()

        if not lib_path.exists() or not lib_path.is_dir():
            logger.warning(
                "library path does not exist or is not a directory", path=lib_path
            )
            return LibraryScanOutput(episodes=results, font_directories=list(font_dirs))

        # Find all MKV files recursively, sort them for deterministic order
        mkv_files = sorted(
            [p for p in lib_path.rglob("*.mkv") if not _is_excluded(p, lib_path)],
            key=lambda p: p.name,
        )

        for mkv in mkv_files:
            parent = mkv.parent

            # Scan parent's subdirectories for "fonts" or "Fonts" case-insensitively
            try:
                for child in parent.iterdir():
                    if child.is_dir() and child.name.lower() == "fonts":
                        resolved_child = child.resolve()
                        if not _is_excluded(resolved_child, lib_path):
                            font_dirs.add(resolved_child)
            except Exception as e:
                logger.error(
                    "failed to search for font directories",
                    directory=parent,
                    error=str(e),
                )

            try:
                # List sibling ASS files
                ass_files = [
                    p
                    for p in parent.iterdir()
                    if p.is_file() and p.suffix.lower() == ".ass"
                ]
            except Exception as e:
                logger.error(
                    "failed to list directory contents",
                    directory=parent,
                    error=str(e),
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

        return LibraryScanOutput(
            episodes=results, font_directories=sorted(list(font_dirs))
        )

    return await asyncio.to_thread(_scan)
