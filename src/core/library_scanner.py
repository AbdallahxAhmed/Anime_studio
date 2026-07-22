import asyncio
from pathlib import Path
import re
from difflib import SequenceMatcher
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any
import structlog
from src.models.pipeline import (
    EmbeddedTrack,
    EmbeddedSubInfo,
    LibraryScanResult,
    LibraryScanOutput,
)
from src.models.subtitle import SubtitleSource
from src.errors import PipelineStoppedError

if TYPE_CHECKING:
    from src.ports.mkvmerge import MkvmergePort
    from src.models.pipeline import ShowNode

logger = structlog.get_logger()


def _raise_if_stopped(stop_event: asyncio.Event | None) -> None:
    """Abort the current scan invocation when its caller requests a stop."""
    if stop_event is not None and stop_event.is_set():
        raise PipelineStoppedError("Library scan stopped by user")


def _list_directory_entries(directory: Path) -> tuple[tuple[Path, bool, bool], ...]:
    """List one directory without consulting run state.

    This intentionally small blocking unit is the only filesystem work sent to a
    worker during Phase 1.  Cancellation remains exclusively on the event-loop
    thread before and after the call.
    """
    entries: list[tuple[Path, bool, bool]] = []
    for child in sorted(directory.iterdir(), key=lambda path: path.name.casefold()):
        try:
            entries.append((child, child.is_dir(), child.is_file()))
        except OSError:
            # A concurrently removed or inaccessible child is handled by the
            # normal best-effort scanner behavior.
            continue
    return tuple(entries)


async def _cooperative_checkpoint(stop_event: asyncio.Event | None) -> None:
    """Yield to Qt/qasync after a bounded scan unit and re-check Stop."""
    _raise_if_stopped(stop_event)
    await asyncio.sleep(0)
    _raise_if_stopped(stop_event)


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


_AMUX_TEMP_RE = re.compile(r"^_amux_.*\.tmp\.\w+$", re.IGNORECASE)


def _is_excluded(path: Path, base: Path) -> bool:
    """Return True if any path component relative to base starts with '.' or if the filename matches the _amux_ temp file pattern."""
    try:
        relative = path.relative_to(base)
    except ValueError:
        return False
    if any(part.startswith(".") for part in relative.parts):
        return True
    if _AMUX_TEMP_RE.match(path.name):
        return True
    return False


def _is_ancestor(ancestor: Path, descendant: Path) -> bool:
    try:
        descendant.relative_to(ancestor)
        return True
    except ValueError:
        return False


def _parse_embedded_info(identify_result: dict[str, Any]) -> EmbeddedSubInfo | None:
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

    async def _build_show_tree(
        self,
        lib_path: Path,
        scan_results: list[LibraryScanResult],
        stop_event: asyncio.Event | None = None,
    ) -> list["ShowNode"]:
        """Build the library tree using the same bounded async directory walk."""
        from src.models.pipeline import ShowNode, SubFolderNode, EpisodeContext

        episodes_by_path = {
            ep.episode_path: EpisodeContext(scan_result=ep) for ep in scan_results
        }

        show_nodes = []
        _raise_if_stopped(stop_event)
        try:
            root_entries = await asyncio.to_thread(_list_directory_entries, lib_path)
        except OSError:
            return []
        _raise_if_stopped(stop_event)
        top_dirs = [
            path
            for path, is_directory, _ in root_entries
            if is_directory and not _is_excluded(path, lib_path)
        ]

        for show_dir in top_dirs:
            _raise_if_stopped(stop_event)
            resolved_show = show_dir.resolve()
            sub_folders = []
            try:
                show_entries = await asyncio.to_thread(
                    _list_directory_entries, show_dir
                )
            except OSError:
                show_entries = ()
            _raise_if_stopped(stop_event)
            sub_dirs = [
                path
                for path, is_directory, _ in show_entries
                if is_directory and not _is_excluded(path, lib_path)
            ]

            for sub_dir in sub_dirs:
                _raise_if_stopped(stop_event)
                resolved_sub = sub_dir.resolve()
                sub_episodes = tuple(
                    ep_ctx
                    for ep_path, ep_ctx in episodes_by_path.items()
                    if ep_path.parent == resolved_sub
                    or _is_ancestor(resolved_sub, ep_path)
                )
                if sub_episodes:
                    sub_folders.append(
                        SubFolderNode(
                            name=sub_dir.name,
                            path=resolved_sub,
                            episodes=sub_episodes,
                        )
                    )
                await _cooperative_checkpoint(stop_event)

            direct_episodes = tuple(
                ep_ctx
                for ep_path, ep_ctx in episodes_by_path.items()
                if ep_path.parent == resolved_show
            )

            if direct_episodes or sub_folders:
                show_nodes.append(
                    ShowNode(
                        name=show_dir.name,
                        path=resolved_show,
                        sub_folders=tuple(sub_folders),
                        episodes=direct_episodes,
                    )
                )
            await _cooperative_checkpoint(stop_event)

        return show_nodes

    async def scan_folder(
        self, folder_path: Path, stop_event: asyncio.Event | None = None
    ) -> LibraryScanOutput:
        """Scan a single show folder without touching the full library."""
        lib_path = Path(folder_path).resolve()

        # Phase 1: Filesystem walk — match external .ass files
        _raise_if_stopped(stop_event)
        phase1_results, font_dirs, unmatched_mkvs = await self._phase1_walk(
            lib_path, stop_event
        )
        _raise_if_stopped(stop_event)

        # Phase 2: Embedded detection for unmatched MKVs (async)
        phase2_results = []
        if self._mkvmerge and unmatched_mkvs:
            phase2_results = await self._phase2_embedded_detection(
                unmatched_mkvs, lib_path, stop_event
            )

        _raise_if_stopped(stop_event)
        all_results = phase1_results + phase2_results
        sorted_results = sorted(all_results, key=lambda r: r.episode_path.name)
        return LibraryScanOutput(
            episodes=sorted_results,
            font_directories=sorted(list(font_dirs)),
            show_tree=(),
        )

    async def scan(
        self, library_path: Path, stop_event: asyncio.Event | None = None
    ) -> LibraryScanOutput:
        """Scan the library_path for MKV files, matching ASS subtitle
        siblings, Fonts directories, and embedded subtitle tracks."""

        lib_path = Path(library_path).resolve()

        # Phase 1: Filesystem walk — match external .ass files
        _raise_if_stopped(stop_event)
        phase1_results, font_dirs, unmatched_mkvs = await self._phase1_walk(
            lib_path, stop_event
        )
        _raise_if_stopped(stop_event)

        # Phase 2: Embedded detection for unmatched MKVs (async)
        phase2_results = []
        if self._mkvmerge and unmatched_mkvs:
            phase2_results = await self._phase2_embedded_detection(
                unmatched_mkvs, lib_path, stop_event
            )

        _raise_if_stopped(stop_event)
        all_results = phase1_results + phase2_results
        sorted_results = sorted(all_results, key=lambda r: r.episode_path.name)
        show_tree = await self._build_show_tree(lib_path, sorted_results, stop_event)
        _raise_if_stopped(stop_event)
        return LibraryScanOutput(
            episodes=sorted_results,
            font_directories=sorted(list(font_dirs)),
            show_tree=tuple(show_tree),
        )

    async def _phase1_walk(
        self, lib_path: Path, stop_event: asyncio.Event | None = None
    ) -> tuple[list[LibraryScanResult], set[Path], list[tuple[Path, str]]]:
        """Walk the filesystem to find MKV-ASS pairs and font directories.

        Returns:
            Tuple of (matched_results, font_directories, unmatched_mkvs)
            where unmatched_mkvs is a list of (mkv_path, anime_title) tuples.
        """
        results: list[LibraryScanResult] = []
        font_dirs: set[Path] = set()
        unmatched_mkvs: list[tuple[Path, str]] = []

        _raise_if_stopped(stop_event)
        if not await asyncio.to_thread(lib_path.is_dir):
            _raise_if_stopped(stop_event)
            logger.warning(
                "library path does not exist or is not a directory", path=lib_path
            )
            return results, font_dirs, unmatched_mkvs

        # Group MKV files by parent directory to scan siblings efficiently.  The
        # event loop owns cancellation; workers list exactly one directory and
        # never receive the asyncio.Event.
        mkv_by_parent: dict[Path, list[Path]] = defaultdict(list)
        entries_by_parent: dict[Path, tuple[tuple[Path, bool, bool], ...]] = {}
        directories: deque[Path] = deque([lib_path])
        while directories:
            _raise_if_stopped(stop_event)
            directory = directories.popleft()
            try:
                children = await asyncio.to_thread(_list_directory_entries, directory)
            except OSError as e:
                logger.error(
                    "failed to list directory contents",
                    directory=directory,
                    error=str(e),
                )
                continue
            _raise_if_stopped(stop_event)
            entries_by_parent[directory] = children
            for child, is_directory, is_file in children:
                _raise_if_stopped(stop_event)
                if _is_excluded(child, lib_path):
                    continue
                if is_directory:
                    directories.append(child)
                elif is_file and child.suffix.lower() == ".mkv":
                    mkv_by_parent[child.parent].append(child)
            await _cooperative_checkpoint(stop_event)

        for parent in sorted(mkv_by_parent):
            _raise_if_stopped(stop_event)
            parent_mkv_files = mkv_by_parent[parent]
            sibling_entries = entries_by_parent.get(parent, ())

            # Check every sibling explicitly.  This deliberately avoids a
            # comprehension that could traverse a large directory without
            # giving Stop a chance to run.
            ass_files: list[Path] = []
            for child, is_directory, is_file in sibling_entries:
                _raise_if_stopped(stop_event)
                if is_directory and child.name.lower() == "fonts":
                    resolved_child = child.resolve()
                    if not _is_excluded(resolved_child, lib_path):
                        font_dirs.add(resolved_child)
                elif is_file and child.suffix.lower() == ".ass":
                    ass_files.append(child)
            await _cooperative_checkpoint(stop_event)

            # 1st Pass: Match by exact name or extracted episode number
            mkv_by_info: dict[tuple[int, int], Path] = {}
            for mkv in parent_mkv_files:
                _raise_if_stopped(stop_event)
                info = get_info(mkv.name)
                if info:
                    mkv_by_info[info] = mkv
            await _cooperative_checkpoint(stop_event)

            matched_ass: set[Path] = set()
            matched_mkv: set[Path] = set()

            # First, check if exact name match works (fast path and highest priority)
            for mkv in parent_mkv_files:
                _raise_if_stopped(stop_event)
                mkv_stem = mkv.stem.lower()
                for ass in ass_files:
                    _raise_if_stopped(stop_event)
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
                await _cooperative_checkpoint(stop_event)

            # Next, match by extracted episode number for unmatched files
            for ass in ass_files:
                _raise_if_stopped(stop_event)
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
                await _cooperative_checkpoint(stop_event)

            # 2nd Pass: Fuzzy matching for the leftovers
            for mkv in parent_mkv_files:
                _raise_if_stopped(stop_event)
                if mkv in matched_mkv:
                    continue
                sig_v = signature(mkv.stem)
                best_ass = None
                best_r = 0.0
                for ass in ass_files:
                    _raise_if_stopped(stop_event)
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
                await _cooperative_checkpoint(stop_event)

            # Collect unmatched MKVs for Phase 2 embedded detection
            for mkv in parent_mkv_files:
                _raise_if_stopped(stop_event)
                if mkv not in matched_mkv:
                    anime_title = parent.name if parent.name else "Unknown"
                    unmatched_mkvs.append((mkv.resolve(), anime_title))
                    logger.debug(
                        "no matching ASS subtitle sibling for MKV", mkv=mkv.name
                    )
            await _cooperative_checkpoint(stop_event)

        return results, font_dirs, unmatched_mkvs

    async def _phase2_embedded_detection(
        self,
        unmatched_mkvs: list[tuple[Path, str]],
        lib_path: Path,
        stop_event: asyncio.Event | None = None,
    ) -> list[LibraryScanResult]:
        """Detect embedded ASS subtitle tracks in unmatched MKVs via mkvmerge -J.

        Runs up to 4 concurrent mkvmerge identify calls to avoid spawning
        too many subprocesses.
        """
        mkvmerge = self._mkvmerge
        assert mkvmerge is not None

        _raise_if_stopped(stop_event)
        results: list[LibraryScanResult] = []

        async def _detect_one(
            mkv_path: Path, anime_title: str
        ) -> LibraryScanResult | None:
            _raise_if_stopped(stop_event)
            try:
                identify_result = await mkvmerge.identify(mkv_path)
            except asyncio.CancelledError:
                raise
            except PipelineStoppedError:
                raise
            except Exception as e:
                logger.warning(
                    "mkvmerge identify failed for embedded sub detection",
                    mkv=mkv_path.name,
                    error=str(e),
                )
                return None

            _raise_if_stopped(stop_event)
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

        pending: set[asyncio.Task[LibraryScanResult | None]] = set()
        candidates = iter(unmatched_mkvs)

        async def _drain_owned_tasks(*, cancel: bool) -> None:
            """Consume every task this invocation owns before returning."""
            if cancel:
                for task in pending:
                    if not task.done():
                        task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        def _schedule_next() -> bool:
            _raise_if_stopped(stop_event)
            try:
                mkv_path, anime_title = next(candidates)
            except StopIteration:
                return False
            pending.add(asyncio.create_task(_detect_one(mkv_path, anime_title)))
            return True

        try:
            for _ in range(min(4, len(unmatched_mkvs))):
                _schedule_next()

            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                stopped = stop_event is not None and stop_event.is_set()
                native_cancelled = False
                for task in done:
                    try:
                        result = task.result()
                    except asyncio.CancelledError:
                        # Consume every completed task before propagating native
                        # cancellation; otherwise a sibling exception can be
                        # left un-retrieved.
                        native_cancelled = True
                    except PipelineStoppedError:
                        stopped = True
                    else:
                        if result is not None:
                            results.append(result)

                if native_cancelled:
                    raise asyncio.CancelledError

                if stopped:
                    # A user Stop never cancels in-flight binary work.  Wait
                    # for every owned task, discard their results, and return a
                    # neutral stopped outcome.
                    await _drain_owned_tasks(cancel=False)
                    raise PipelineStoppedError("Library scan stopped by user")

                while len(pending) < 4 and _schedule_next():
                    pass
        except asyncio.CancelledError:
            # Native cancellation does cancel owned tasks, then consumes every
            # outcome so no task exception is left un-retrieved.
            await _drain_owned_tasks(cancel=True)
            raise
        except PipelineStoppedError:
            await _drain_owned_tasks(cancel=False)
            raise

        return results
