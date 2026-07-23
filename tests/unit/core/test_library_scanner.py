import asyncio
import threading
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from src.core.library_scanner import LibraryScanner, _parse_embedded_info
from src.errors import PipelineStoppedError
from src.models.pipeline import LibraryScanOutput
from src.models.subtitle import SubtitleSource


@pytest.mark.anyio
async def test_scan_library_empty(tmp_path):
    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    assert isinstance(results, LibraryScanOutput)
    assert len(results.episodes) == 0
    assert len(results.font_directories) == 0


@pytest.mark.anyio
async def test_scan_stops_before_filesystem_traversal(tmp_path):
    """A pre-set stop signal produces no successful scan output or identify call."""
    mkvmerge = AsyncMock()
    scanner = LibraryScanner(mkvmerge=mkvmerge)
    stop_event = asyncio.Event()
    stop_event.set()

    with pytest.raises(PipelineStoppedError):
        await scanner.scan(tmp_path, stop_event=stop_event)

    mkvmerge.identify.assert_not_called()


@pytest.mark.anyio
async def test_scan_stops_during_phase1_without_returning_partial_output(
    tmp_path, monkeypatch
):
    """Phase 1 checks the stop signal between pairing units."""
    show = tmp_path / "Show"
    show.mkdir()
    (show / "episode_01.mkv").touch()
    (show / "episode_02.mkv").touch()
    (show / "subtitle.ass").touch()
    stop_event = asyncio.Event()

    from src.core import library_scanner

    original_get_info = library_scanner.get_info

    def stop_after_first_info(filename: str):
        stop_event.set()
        return original_get_info(filename)

    monkeypatch.setattr(library_scanner, "get_info", stop_after_first_info)

    with pytest.raises(PipelineStoppedError):
        await LibraryScanner().scan(tmp_path, stop_event=stop_event)


@pytest.mark.anyio
async def test_phase1_stop_is_processed_while_worker_lists_one_directory(
    tmp_path, monkeypatch
):
    """Stop remains event-loop owned while one bounded filesystem call runs."""
    show = tmp_path / "Show"
    show.mkdir()
    (show / "episode_01.mkv").touch()
    (show / "episode_01.ass").touch()
    stop_event = asyncio.Event()
    listing_started = asyncio.Event()
    release_listing = threading.Event()

    from src.core import library_scanner

    original_list = library_scanner._list_directory_entries
    loop = asyncio.get_running_loop()

    def controlled_list(directory: Path):
        if directory == tmp_path:
            loop.call_soon_threadsafe(listing_started.set)
            release_listing.wait()
        return original_list(directory)

    monkeypatch.setattr(library_scanner, "_list_directory_entries", controlled_list)
    scan_task = asyncio.create_task(
        LibraryScanner().scan(tmp_path, stop_event=stop_event)
    )
    await listing_started.wait()
    stop_event.set()
    release_listing.set()

    with pytest.raises(PipelineStoppedError):
        await scan_task


@pytest.mark.anyio
async def test_phase1_stops_after_checked_ass_iteration_before_pairing(
    tmp_path, monkeypatch
):
    """A large sibling set never becomes an unchecked ASS comprehension."""
    show = tmp_path / "Show"
    show.mkdir()
    (show / "episode_01.mkv").touch()
    for index in range(3):
        (show / f"subtitle_{index:02d}.ass").touch()
    stop_event = asyncio.Event()

    from src.core import library_scanner

    original_checkpoint = library_scanner._cooperative_checkpoint
    checkpoints = 0

    async def stop_after_sibling_iteration(event: asyncio.Event | None) -> None:
        nonlocal checkpoints
        checkpoints += 1
        # Root walk, show walk, then sibling ASS iteration.
        if checkpoints == 3:
            stop_event.set()
        await original_checkpoint(event)

    original_get_info = library_scanner.get_info
    get_info_calls = 0

    def count_get_info(filename: str):
        nonlocal get_info_calls
        get_info_calls += 1
        return original_get_info(filename)

    monkeypatch.setattr(library_scanner, "get_info", count_get_info)
    monkeypatch.setattr(
        library_scanner, "_cooperative_checkpoint", stop_after_sibling_iteration
    )

    with pytest.raises(PipelineStoppedError):
        await LibraryScanner().scan(tmp_path, stop_event=stop_event)

    assert get_info_calls == 0


@pytest.mark.anyio
async def test_embedded_detection_stops_before_scheduling_later_batches():
    """Running identifies finish naturally, while no post-stop unit is created."""
    first_batch_started = asyncio.Event()
    release_identifies = asyncio.Event()
    started: list[Path] = []

    async def identify(path: Path):
        started.append(path)
        if len(started) == 4:
            first_batch_started.set()
        await release_identifies.wait()
        return {"tracks": [], "attachments": []}

    mkvmerge = AsyncMock()
    mkvmerge.identify.side_effect = identify
    scanner = LibraryScanner(mkvmerge=mkvmerge)
    stop_event = asyncio.Event()
    candidates = [(Path(f"/library/{i}.mkv"), "Show") for i in range(5)]

    phase2_task = asyncio.create_task(
        scanner._phase2_embedded_detection(candidates, Path("/library"), stop_event)
    )
    await first_batch_started.wait()
    stop_event.set()
    release_identifies.set()

    with pytest.raises(PipelineStoppedError):
        await phase2_task

    assert started == [Path(f"/library/{i}.mkv") for i in range(4)]


@pytest.mark.anyio
async def test_embedded_detection_reraises_neutral_stop_from_identify():
    """A neutral stop from the binary boundary is never treated as a warning."""
    mkvmerge = AsyncMock()
    mkvmerge.identify.side_effect = PipelineStoppedError("identify stopped")
    scanner = LibraryScanner(mkvmerge=mkvmerge)

    with pytest.raises(PipelineStoppedError):
        await scanner._phase2_embedded_detection(
            [(Path("/library/episode.mkv"), "Show")], Path("/library")
        )


@pytest.mark.anyio
async def test_embedded_detection_native_cancellation_cleans_all_owned_tasks():
    """Native cancellation cancels and awaits every in-flight identify task."""
    first_batch_started = asyncio.Event()
    cancelled_paths: list[Path] = []
    started: list[Path] = []
    never_complete = asyncio.Event()

    async def identify(path: Path):
        started.append(path)
        if len(started) == 4:
            first_batch_started.set()
        try:
            await never_complete.wait()
        except asyncio.CancelledError:
            cancelled_paths.append(path)
            raise
        raise AssertionError("identify operation unexpectedly completed")

    mkvmerge = AsyncMock()
    mkvmerge.identify.side_effect = identify
    scanner = LibraryScanner(mkvmerge=mkvmerge)
    candidates = [(Path(f"/library/{index}.mkv"), "Show") for index in range(5)]
    phase2_task = asyncio.create_task(
        scanner._phase2_embedded_detection(candidates, Path("/library"))
    )
    await first_batch_started.wait()
    phase2_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await phase2_task

    assert started == [Path(f"/library/{index}.mkv") for index in range(4)]
    assert set(cancelled_paths) == set(started)


@pytest.mark.anyio
async def test_scan_library_matching(tmp_path):
    # Setup matching MKV/ASS pair
    anime_dir = tmp_path / "Cool Anime"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    ass = anime_dir / "episode_01.ass"
    mkv.touch()
    ass.touch()

    # MKV without ASS
    mkv_no_ass = anime_dir / "episode_02.mkv"
    mkv_no_ass.touch()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    assert len(results.episodes) == 1
    assert results.episodes[0].episode_path == mkv.resolve()
    assert results.episodes[0].subtitle_path == ass.resolve()
    assert results.episodes[0].anime_title == "Cool Anime"
    assert results.episodes[0].subtitle_source == SubtitleSource.EXTERNAL


@pytest.mark.anyio
async def test_scan_library_case_insensitive(tmp_path):
    anime_dir = tmp_path / "Cool Anime"
    anime_dir.mkdir()
    # Different case for stem / extension
    mkv = anime_dir / "EPISODE_01.MKV"
    ass = anime_dir / "episode_01.ASS"
    mkv.touch()
    ass.touch()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    assert len(results.episodes) == 1
    assert results.episodes[0].episode_path == mkv.resolve()
    assert results.episodes[0].subtitle_path == ass.resolve()
    assert results.episodes[0].anime_title == "Cool Anime"


@pytest.mark.anyio
async def test_scan_library_font_directory_detection(tmp_path):
    # Setup matching MKV/ASS pair with sibling Fonts/ folder
    anime_dir = tmp_path / "Cool Anime"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    ass = anime_dir / "episode_01.ass"
    mkv.touch()
    ass.touch()

    fonts_dir = anime_dir / "Fonts"
    fonts_dir.mkdir()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    assert len(results.episodes) == 1
    assert len(results.font_directories) == 1
    assert results.font_directories[0] == fonts_dir.resolve()


@pytest.mark.anyio
async def test_scan_library_font_directory_case_insensitive(tmp_path):
    anime_dir = tmp_path / "Cool Anime"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    ass = anime_dir / "episode_01.ass"
    mkv.touch()
    ass.touch()

    fonts_dir = anime_dir / "fonts"  # lowercase
    fonts_dir.mkdir()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    assert len(results.episodes) == 1
    assert len(results.font_directories) == 1
    assert results.font_directories[0] == fonts_dir.resolve()


@pytest.mark.anyio
async def test_scan_library_no_font_directory(tmp_path):
    anime_dir = tmp_path / "Cool Anime"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    ass = anime_dir / "episode_01.ass"
    mkv.touch()
    ass.touch()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    assert len(results.episodes) == 1
    assert len(results.font_directories) == 0


def test_is_excluded():
    from src.core.library_scanner import _is_excluded

    base = Path("/test/library")
    assert _is_excluded(base / ".anime_studio_trash" / "ep01.mkv", base) is True
    assert (
        _is_excluded(base / "show" / ".anime_studio_trash" / "ep01.mkv", base) is True
    )
    assert _is_excluded(base / ".git" / "config", base) is True
    assert _is_excluded(base / "show" / "episode_01.mkv", base) is False
    assert _is_excluded(base / "show" / "Fonts" / "font.ttf", base) is False


def test_is_excluded_amux_temp_file():
    from src.core.library_scanner import _is_excluded

    base = Path("/test/library")
    assert _is_excluded(base / "_amux_ep01.tmp.mkv", base) is True
    assert _is_excluded(base / "_amux_ep01.tmp.ass", base) is True
    assert _is_excluded(base / "_amux_abc123.tmp.mkv", base) is True
    assert _is_excluded(base / "amux_regular.mkv", base) is False
    assert _is_excluded(base / "episode.tmp.mkv", base) is False
    assert _is_excluded(base / "episode01.mkv", base) is False


@pytest.mark.anyio
async def test_scan_library_excludes_dot_directories(tmp_path):
    # Setup standard show with matching pair
    show_dir = tmp_path / "Show A"
    show_dir.mkdir()
    mkv = show_dir / "episode_01.mkv"
    ass = show_dir / "episode_01.ass"
    mkv.touch()
    ass.touch()

    # Trash directory inside show
    trash_dir = show_dir / ".anime_studio_trash"
    trash_dir.mkdir()
    trash_mkv = trash_dir / "episode_01.mkv"
    trash_ass = trash_dir / "episode_01.ass"
    trash_mkv.touch()
    trash_ass.touch()

    # Hidden folder in base
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_mkv = git_dir / "secret.mkv"
    git_ass = git_dir / "secret.ass"
    git_mkv.touch()
    git_ass.touch()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    # Only the main show's episode should be found
    assert len(results.episodes) == 1
    assert results.episodes[0].episode_path == mkv.resolve()
    assert results.episodes[0].subtitle_path == ass.resolve()


@pytest.mark.anyio
async def test_scan_library_excludes_dot_font_directories(tmp_path):
    # Setup standard show with matching pair
    show_dir = tmp_path / "Show A"
    show_dir.mkdir()
    mkv = show_dir / "episode_01.mkv"
    ass = show_dir / "episode_01.ass"
    mkv.touch()
    ass.touch()

    # Standard Font dir
    fonts_dir = show_dir / "Fonts"
    fonts_dir.mkdir()

    # Trash font directory
    trash_dir = show_dir / ".anime_studio_trash"
    trash_dir.mkdir()
    trash_mkv = trash_dir / "episode_01.mkv"
    trash_ass = trash_dir / "episode_01.ass"
    trash_mkv.touch()
    trash_ass.touch()
    trash_fonts_dir = trash_dir / "Fonts"
    trash_fonts_dir.mkdir()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    # Only standard fonts dir should be detected, trash fonts dir excluded
    assert len(results.font_directories) == 1
    assert results.font_directories[0] == fonts_dir.resolve()


def test_episode_number_extraction():
    from src.core.library_scanner import get_info

    assert get_info("[SubsPlease] Show Name - 01 (1080p) [12345678].mkv") == (1, 1)
    assert get_info("Show_Name_S02E05_10bit.mkv") == (2, 5)
    assert get_info("Show Name - Episode 12.ass") == (1, 12)
    assert get_info("Show Name - 03v2.ass") == (1, 3)


@pytest.mark.anyio
async def test_scan_library_fuzzy_pairing(tmp_path):
    # Setup matching mismatched files
    anime_dir = tmp_path / "Cool Anime"
    anime_dir.mkdir()

    # 1. Matching by episode extraction
    mkv1 = anime_dir / "[SubsPlease] Cool Anime - 03 (1080p) [12345678].mkv"
    ass1 = anime_dir / "Cool Anime - Episode 03 Arabic.ass"
    mkv1.touch()
    ass1.touch()

    # 2. Matching by signature / fuzzy match (SequenceMatcher)
    mkv2 = anime_dir / "Cool_Anime_Movie_Special_Edition.mkv"
    ass2 = anime_dir / "Cool Anime Movie Arabic Sub.ass"
    mkv2.touch()
    ass2.touch()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)
    # Both pairs should be successfully matched!
    assert len(results.episodes) == 2

    # Sort results by episode path to ensure order for assert
    sorted_eps = sorted(results.episodes, key=lambda e: e.episode_path.name)

    # "Cool_Anime_Movie_Special_Edition.mkv" comes first alphabetically
    assert sorted_eps[0].episode_path == mkv2.resolve()
    assert sorted_eps[0].subtitle_path == ass2.resolve()

    # "[SubsPlease] Cool Anime..." comes second
    assert sorted_eps[1].episode_path == mkv1.resolve()
    assert sorted_eps[1].subtitle_path == ass1.resolve()


# --- Embedded subtitle detection tests ---


def test_parse_embedded_info_with_ass_tracks():
    """Test parsing mkvmerge -J output with ASS subtitle tracks."""
    identify_result = {
        "tracks": [
            {"type": "video", "codec": "HEVC"},
            {
                "type": "subtitles",
                "codec": "SubStationAlpha",
                "properties": {
                    "codec_id": "S_TEXT/ASS",
                    "language": "jpn",
                },
            },
            {
                "type": "subtitles",
                "codec": "SubStationAlpha",
                "properties": {
                    "codec_id": "S_TEXT/ASS",
                    "language": "eng",
                },
            },
            {"type": "audio", "codec": "AAC"},
        ],
        "attachments": [
            {"content_type": "application/x-truetype-font", "file_name": "Arial.ttf"},
            {"content_type": "font/otf", "file_name": "CustomFont.otf"},
        ],
    }

    info = _parse_embedded_info(identify_result)
    assert info is not None
    assert info.track_count == 2
    assert info.languages == ["jpn", "eng"]
    assert info.has_embedded_fonts is True
    assert info.embedded_font_names == ["Arial.ttf", "CustomFont.otf"]


def test_parse_embedded_info_no_ass_tracks():
    """Test parsing mkvmerge -J output with no ASS tracks."""
    identify_result = {
        "tracks": [
            {"type": "video", "codec": "HEVC"},
            {
                "type": "subtitles",
                "codec": "SRT",
                "properties": {"codec_id": "S_TEXT/UTF8", "language": "eng"},
            },
        ],
        "attachments": [],
    }

    info = _parse_embedded_info(identify_result)
    assert info is None


def test_parse_embedded_info_empty():
    """Test parsing empty mkvmerge -J output."""
    info = _parse_embedded_info({})
    assert info is None


@pytest.mark.anyio
async def test_scan_folder_is_confined_to_selected_show_and_identifies_once(tmp_path):
    """Add Folder never enumerates or identifies sibling show media."""
    show_a = tmp_path / "Show A"
    show_b = tmp_path / "Show B"
    show_a.mkdir()
    show_b.mkdir()
    selected = [show_a / f"a{number}.mkv" for number in range(1, 4)]
    siblings = [show_b / f"b{number}.mkv" for number in range(1, 3)]
    for media in [*selected, *siblings]:
        media.touch()

    mkvmerge = AsyncMock(return_value={"tracks": []})
    mkvmerge.identify.side_effect = lambda path: {"tracks": []}
    scanner = LibraryScanner(mkvmerge=mkvmerge)

    result = await scanner.scan_folder(show_a)

    assert result.episodes == []
    identified = [call.args[0] for call in mkvmerge.identify.call_args_list]
    assert identified == [path.resolve() for path in selected]
    assert not set(identified).intersection(path.resolve() for path in siblings)


async def test_scan_without_mkvmerge_port(tmp_path):
    """Scanner without mkvmerge port behaves identically to legacy scan_library."""
    anime_dir = tmp_path / "Show A"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    mkv.touch()
    # No ASS file — would be unmatched

    scanner = LibraryScanner(mkvmerge=None)
    results = await scanner.scan(tmp_path)
    # Without mkvmerge, unmatched MKVs are just skipped — no embedded detection
    assert len(results.episodes) == 0


@pytest.mark.anyio
async def test_scan_with_embedded_subs_found(tmp_path):
    """Scanner detects embedded ASS tracks via mkvmerge port."""
    anime_dir = tmp_path / "Show A"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    mkv.touch()
    # No external ASS file

    mock_mkvmerge = AsyncMock()
    mock_mkvmerge.identify.return_value = {
        "tracks": [
            {"type": "video", "codec": "HEVC"},
            {
                "type": "subtitles",
                "codec": "SubStationAlpha",
                "properties": {
                    "codec_id": "S_TEXT/ASS",
                    "language": "jpn",
                },
            },
        ],
        "attachments": [
            {"content_type": "application/x-truetype-font", "file_name": "Font.ttf"},
        ],
    }

    scanner = LibraryScanner(mkvmerge=mock_mkvmerge)
    results = await scanner.scan(tmp_path)

    assert len(results.episodes) == 1
    ep = results.episodes[0]
    assert ep.subtitle_source == SubtitleSource.EMBEDDED
    assert ep.subtitle_path is None
    assert ep.embedded_sub_info is not None
    assert ep.embedded_sub_info.track_count == 1
    assert ep.embedded_sub_info.languages == ["jpn"]
    assert ep.embedded_sub_info.has_embedded_fonts is True
    assert ep.embedded_sub_info.embedded_font_names == ["Font.ttf"]

    mock_mkvmerge.identify.assert_called_once_with(mkv.resolve())


@pytest.mark.anyio
async def test_scan_with_both_external_and_embedded(tmp_path):
    """When both external and embedded subs exist, external takes priority."""
    anime_dir = tmp_path / "Show A"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    ass = anime_dir / "episode_01.ass"
    mkv.touch()
    ass.touch()

    mock_mkvmerge = AsyncMock()
    # Should NOT be called because the MKV is matched to external ASS
    scanner = LibraryScanner(mkvmerge=mock_mkvmerge)
    results = await scanner.scan(tmp_path)

    assert len(results.episodes) == 1
    ep = results.episodes[0]
    assert ep.subtitle_source == SubtitleSource.EXTERNAL
    assert ep.subtitle_path == ass.resolve()
    # mkvmerge should NOT have been called for matched MKVs
    mock_mkvmerge.identify.assert_not_called()


@pytest.mark.anyio
async def test_scan_with_mkvmerge_failure(tmp_path):
    """Scanner gracefully handles mkvmerge identify failure."""
    anime_dir = tmp_path / "Show A"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    mkv.touch()
    # No external ASS file

    mock_mkvmerge = AsyncMock()
    mock_mkvmerge.identify.side_effect = Exception("mkvmerge crashed")

    scanner = LibraryScanner(mkvmerge=mock_mkvmerge)
    results = await scanner.scan(tmp_path)

    # Should not crash — just log warning and return empty
    assert len(results.episodes) == 0
    mock_mkvmerge.identify.assert_called_once()


@pytest.mark.anyio
async def test_scan_with_no_embedded_ass(tmp_path):
    """Scanner handles MKV with no embedded ASS tracks (e.g., only SRT)."""
    anime_dir = tmp_path / "Show A"
    anime_dir.mkdir()
    mkv = anime_dir / "episode_01.mkv"
    mkv.touch()

    mock_mkvmerge = AsyncMock()
    mock_mkvmerge.identify.return_value = {
        "tracks": [
            {"type": "video", "codec": "HEVC"},
            {
                "type": "subtitles",
                "codec": "SRT",
                "properties": {"codec_id": "S_TEXT/UTF8", "language": "eng"},
            },
        ],
        "attachments": [],
    }

    scanner = LibraryScanner(mkvmerge=mock_mkvmerge)
    results = await scanner.scan(tmp_path)
    # SRT tracks should not be detected as ASS
    assert len(results.episodes) == 0


@pytest.mark.anyio
async def test_scan_library_builds_show_tree(tmp_path):
    # Setup directory layout:
    # tmp_path/
    #   Show A/
    #     episode_01.mkv
    #     episode_01.ass
    #     Season 1/
    #       episode_02.mkv
    #       episode_02.ass
    #   Show B/
    #     episode_03.mkv
    #     episode_03.ass

    show_a = tmp_path / "Show A"
    show_a.mkdir()
    (show_a / "episode_01.mkv").touch()
    (show_a / "episode_01.ass").touch()

    season_1 = show_a / "Season 1"
    season_1.mkdir()
    (season_1 / "episode_02.mkv").touch()
    (season_1 / "episode_02.ass").touch()

    show_b = tmp_path / "Show B"
    show_b.mkdir()
    (show_b / "episode_03.mkv").touch()
    (show_b / "episode_03.ass").touch()

    scanner = LibraryScanner()
    results = await scanner.scan(tmp_path)

    # Check show_tree structure
    tree = results.show_tree
    assert len(tree) == 2

    # Sorted by name
    assert tree[0].name == "Show A"
    assert tree[0].path == show_a.resolve()
    assert len(tree[0].episodes) == 1
    assert (
        tree[0].episodes[0].scan_result.episode_path
        == (show_a / "episode_01.mkv").resolve()
    )
    assert len(tree[0].sub_folders) == 1
    assert tree[0].sub_folders[0].name == "Season 1"
    assert tree[0].sub_folders[0].path == season_1.resolve()
    assert len(tree[0].sub_folders[0].episodes) == 1
    assert (
        tree[0].sub_folders[0].episodes[0].scan_result.episode_path
        == (season_1 / "episode_02.mkv").resolve()
    )
    assert tree[0].total_count == 2

    assert tree[1].name == "Show B"
    assert tree[1].path == show_b.resolve()
    assert len(tree[1].episodes) == 1
    assert len(tree[1].sub_folders) == 0
    assert tree[1].total_count == 1
