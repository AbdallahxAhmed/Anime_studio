import asyncio
from pathlib import Path
import re
from difflib import SequenceMatcher
from collections import defaultdict
from typing import TYPE_CHECKING
import structlog
from src.models.pipeline import (
    EmbeddedTrack,
    EmbeddedSubInfo,
    LibraryScanResult,
    LibraryScanOutput,
)
from src.models.subtitle import SubtitleSource

if TYPE_CHECKING:
    from src.ports.mkvmerge import MkvmergePort

logger = structlog.get_logger()


def normalize(name: str) -> str:
    # Replace delimiters with spaces
    name_clean = name.replace("_", " ").replace(".", " ").replace("-", " ")
    # Strip brackets and parens content
    n = re.sub(r"\[.*?\]|\(.*?\)", "", name_clean).lower()
    # Normalize v2/v3 patterns like "03v2" -> "03"
    n = re.sub(r"\b(\d+)v\d+\b", r"\1", n)
    # Strip common anime release descriptors and subtitle markers
    for descriptor in (
        r"special edition",
        r"directors cut",
        r"arabic sub",
        r"eng sub",
        r"softsub",
        r"subbed",
        r"arabic",
        r"english",
        r"sub",
        r"dub",
        r"raw",
    ):
        n = re.sub(rf"\b{descriptor}\b", "", n)
    # Strip technical noise
    for noise in (
        r"1080[pi]?",
        r"720[pi]?",
        r"480[pi]?",
        r"2160[pi]?",
        r"4k",
        r"x264",
        r"x265",
        r"h264",
        r"h265",
        r"hevc",
        r"10bit",
        r"8bit",
        r"web-?dl",
        r"webrip",
        r"bluray",
        r"bdrip",
        r"v2",
        r"v3",
    ):
        n = re.sub(rf"\b{noise}\b", "", n)
    # Collapse multiple spaces
    n = re.sub(r"\s+", " ", n)
    return n.strip()


def get_info(filename: str) -> tuple[int, int] | None:
    c = normalize(filename)
    for pat in (r"s(\d{1,2})[\s\._-]*e(\d{1,4})", r"(\d{1,2})x(\d{1,4})"):
        m = re.search(pat, c)
        if m:
            return int(m.group(1)), int(m.group(2))
    m = re.search(r"(?:ep|episode)[\s\._-]*(\d{1,4})", c)
    if m:
        return 1, int(m.group(1))
    m = re.search(r"-\s*(\d{1,4})\b", c)
    if m:
        return 1, int(m.group(1))
    nums = [int(n) for n in re.findall(r"\b\d{1,4}\b", c) if not (1900 < int(n) < 2100)]
    if nums:
        return 1, nums[-1]
    return None


def signature(name: str) -> str:
    return re.sub(r"\bmovie\b|\b\d+\b", "", normalize(name)).strip()


def _is_excluded(path: Path, base: Path) -> bool:
    """Return True if any path component relative to base starts with '.'."""
    try:
        relative = path.relative_to(base)
    except ValueError:
        return False
    return any(part.startswith(".") for part in relative.parts)


def _parse_embedded_info(identify_result: dict) -> EmbeddedSubInfo | None:
    """Parse mkvmerge -J output into EmbeddedSubInfo.

    Returns None if no ASS/SSA subtitle tracks are found.
    """
    tracks = identify_result.get("tracks", [])
    embedded_tracks = []
    for t in tracks:
        if t.get("type") != "subtitles":
            continue
        codec = (t.get("codec") or "").lower()
        codec_id = (t.get("properties", {}).get("codec_id") or "").lower()
        if (
            "ass" in codec
            or "substation" in codec
            or "ssa" in codec
            or "s_text/ass" in codec_id
        ):
            props = t.get("properties", {})
            embedded_tracks.append(
                EmbeddedTrack(
                    track_id=t.get("id", 0),
                    language=props.get("language", ""),
                    language_ietf=props.get("language_ietf", ""),
                    is_default=props.get("default_track", False),
                    codec=t.get("codec", ""),
                )
            )

    if not embedded_tracks:
        return None

    # Detect embedded font attachments
    embedded_font_names = []
    for a in identify_result.get("attachments", []):
        ct = (a.get("content_type") or "").lower()
        nm = a.get("file_name", "")
        if "font" in ct or nm.lower().endswith((".ttf", ".otf", ".ttc", ".otc")):
            embedded_font_names.append(nm)

    return EmbeddedSubInfo(
        tracks=embedded_tracks,
        has_embedded_fonts=bool(embedded_font_names),
        embedded_font_names=sorted(embedded_font_names),
    )


class LibraryScanner:
    """Scans an anime library for MKV episodes, matching ASS subtitles,
    font directories, and embedded subtitle tracks.

    Args:
        mkvmerge: Optional MkvmergePort for detecting embedded subtitle
            tracks. When None, only external .ass files are detected.
    """

    def __init__(self, mkvmerge: "MkvmergePort | None" = None) -> None:
        self._mkvmerge = mkvmerge

    async def scan(self, library_path: Path) -> LibraryScanOutput:
        """Scan the library_path for MKV files, matching ASS subtitle
        siblings, Fonts directories, and embedded subtitle tracks."""

        lib_path = Path(library_path).resolve()

        # Phase 1: Filesystem walk — match external .ass files
        phase1_results, font_dirs, unmatched_mkvs = await asyncio.to_thread(
            self._phase1_walk, lib_path
        )

        # Phase 2: Embedded detection for unmatched MKVs (async)
        phase2_results = []
        if self._mkvmerge and unmatched_mkvs:
            phase2_results = await self._phase2_embedded_detection(
                unmatched_mkvs, lib_path
            )

        all_results = phase1_results + phase2_results
        return LibraryScanOutput(
            episodes=sorted(all_results, key=lambda r: r.episode_path.name),
            font_directories=sorted(list(font_dirs)),
        )

    def _phase1_walk(
        self, lib_path: Path
    ) -> tuple[list[LibraryScanResult], set[Path], list[tuple[Path, str]]]:
        """Walk the filesystem to find MKV-ASS pairs and font directories.

        Returns:
            Tuple of (matched_results, font_directories, unmatched_mkvs)
            where unmatched_mkvs is a list of (mkv_path, anime_title) tuples.
        """
        results: list[LibraryScanResult] = []
        font_dirs: set[Path] = set()
        unmatched_mkvs: list[tuple[Path, str]] = []

        if not lib_path.exists() or not lib_path.is_dir():
            logger.warning(
                "library path does not exist or is not a directory", path=lib_path
            )
            return results, font_dirs, unmatched_mkvs

        # Group MKV files by parent directory to scan siblings efficiently
        mkv_by_parent: dict[Path, list[Path]] = defaultdict(list)
        for p in lib_path.rglob("*.mkv"):
            if not _is_excluded(p, lib_path):
                mkv_by_parent[p.parent].append(p)

        for parent, parent_mkv_files in mkv_by_parent.items():
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

            # 1st Pass: Match by exact name or extracted episode number
            mkv_by_info: dict[tuple[int, int], Path] = {}
            for mkv in parent_mkv_files:
                info = get_info(mkv.name)
                if info:
                    mkv_by_info[info] = mkv

            matched_ass: set[Path] = set()
            matched_mkv: set[Path] = set()

            # First, check if exact name match works (fast path and highest priority)
            for mkv in parent_mkv_files:
                mkv_stem = mkv.stem.lower()
                for ass in ass_files:
                    if ass not in matched_ass and ass.stem.lower() == mkv_stem:
                        anime_title = parent.name if parent.name else "Unknown"
                        results.append(
                            LibraryScanResult(
                                episode_path=mkv.resolve(),
                                subtitle_path=ass.resolve(),
                                subtitle_source=SubtitleSource.EXTERNAL,
                                anime_title=anime_title,
                            )
                        )
                        matched_ass.add(ass)
                        matched_mkv.add(mkv)
                        logger.info(
                            "discovered episode/subtitle pair (exact)",
                            episode=mkv.name,
                            subtitle=ass.name,
                            anime_title=anime_title,
                        )
                        break

            # Next, match by extracted episode number for unmatched files
            for ass in ass_files:
                if ass in matched_ass:
                    continue
                info = get_info(ass.name)
                if info and info in mkv_by_info:
                    mkv = mkv_by_info[info]
                    if mkv not in matched_mkv:
                        anime_title = parent.name if parent.name else "Unknown"
                        results.append(
                            LibraryScanResult(
                                episode_path=mkv.resolve(),
                                subtitle_path=ass.resolve(),
                                subtitle_source=SubtitleSource.EXTERNAL,
                                anime_title=anime_title,
                            )
                        )
                        matched_ass.add(ass)
                        matched_mkv.add(mkv)
                        logger.info(
                            "discovered episode/subtitle pair (episode info)",
                            episode=mkv.name,
                            subtitle=ass.name,
                            anime_title=anime_title,
                        )

            # 2nd Pass: Fuzzy matching for the leftovers
            for mkv in parent_mkv_files:
                if mkv in matched_mkv:
                    continue
                sig_v = signature(mkv.stem)
                best_ass = None
                best_r = 0.0
                for ass in ass_files:
                    if ass in matched_ass:
                        continue
                    r = SequenceMatcher(None, sig_v, signature(ass.stem)).ratio()
                    if r > best_r and r > 0.6:
                        best_r = r
                        best_ass = ass

                if best_ass:
                    anime_title = parent.name if parent.name else "Unknown"
                    results.append(
                        LibraryScanResult(
                            episode_path=mkv.resolve(),
                            subtitle_path=best_ass.resolve(),
                            subtitle_source=SubtitleSource.EXTERNAL,
                            anime_title=anime_title,
                        )
                    )
                    matched_ass.add(best_ass)
                    matched_mkv.add(mkv)
                    logger.info(
                        "discovered episode/subtitle pair (fuzzy)",
                        episode=mkv.name,
                        subtitle=best_ass.name,
                        anime_title=anime_title,
                    )

            # Collect unmatched MKVs for Phase 2 embedded detection
            for mkv in parent_mkv_files:
                if mkv not in matched_mkv:
                    anime_title = parent.name if parent.name else "Unknown"
                    unmatched_mkvs.append((mkv.resolve(), anime_title))
                    logger.debug(
                        "no matching ASS subtitle sibling for MKV", mkv=mkv.name
                    )

        return results, font_dirs, unmatched_mkvs

    async def _phase2_embedded_detection(
        self,
        unmatched_mkvs: list[tuple[Path, str]],
        lib_path: Path,
    ) -> list[LibraryScanResult]:
        """Detect embedded ASS subtitle tracks in unmatched MKVs via mkvmerge -J.

        Runs up to 4 concurrent mkvmerge identify calls to avoid spawning
        too many subprocesses.
        """
        assert self._mkvmerge is not None

        results: list[LibraryScanResult] = []
        semaphore = asyncio.Semaphore(4)

        async def _detect_one(
            mkv_path: Path, anime_title: str
        ) -> LibraryScanResult | None:
            async with semaphore:
                try:
                    identify_result = await self._mkvmerge.identify(mkv_path)
                except Exception as e:
                    logger.warning(
                        "mkvmerge identify failed for embedded sub detection",
                        mkv=mkv_path.name,
                        error=str(e),
                    )
                    return None

                embedded_info = _parse_embedded_info(identify_result)
                if embedded_info is None:
                    logger.debug(
                        "no embedded ASS tracks found",
                        mkv=mkv_path.name,
                    )
                    return None

                logger.info(
                    "discovered embedded ASS subtitle tracks",
                    mkv=mkv_path.name,
                    track_count=embedded_info.track_count,
                    languages=embedded_info.languages,
                    has_embedded_fonts=embedded_info.has_embedded_fonts,
                )
                return LibraryScanResult(
                    episode_path=mkv_path,
                    subtitle_path=None,
                    subtitle_source=SubtitleSource.EMBEDDED,
                    anime_title=anime_title,
                    embedded_sub_info=embedded_info,
                )

        tasks = [_detect_one(mkv, title) for mkv, title in unmatched_mkvs]
        detection_results = await asyncio.gather(*tasks)

        for result in detection_results:
            if result is not None:
                results.append(result)

        return results
