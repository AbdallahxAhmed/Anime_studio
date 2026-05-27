import pytest
from src.core.library_scanner import scan_library
from src.models.pipeline import LibraryScanOutput


@pytest.mark.anyio
async def test_scan_library_empty(tmp_path):
    results = await scan_library(tmp_path)
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

    results = await scan_library(tmp_path)
    assert len(results.episodes) == 1
    assert results.episodes[0].episode_path == mkv.resolve()
    assert results.episodes[0].subtitle_path == ass.resolve()
    assert results.episodes[0].anime_title == "Cool Anime"


@pytest.mark.anyio
async def test_scan_library_case_insensitive(tmp_path):
    anime_dir = tmp_path / "Cool Anime"
    anime_dir.mkdir()
    # Different case for stem / extension
    mkv = anime_dir / "EPISODE_01.MKV"
    ass = anime_dir / "episode_01.ASS"
    mkv.touch()
    ass.touch()

    results = await scan_library(tmp_path)
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

    results = await scan_library(tmp_path)
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

    results = await scan_library(tmp_path)
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

    results = await scan_library(tmp_path)
    assert len(results.episodes) == 1
    assert len(results.font_directories) == 0
