import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from src.core.library_scanner import LibraryScanner, _parse_embedded_info
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
