import pytest
from src.core.library_scanner import scan_library


@pytest.mark.anyio
async def test_scan_library_empty(tmp_path):
    results = await scan_library(tmp_path)
    assert len(results) == 0


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
    assert len(results) == 1
    assert results[0].episode_path == mkv.resolve()
    assert results[0].subtitle_path == ass.resolve()
    assert results[0].anime_title == "Cool Anime"


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
    assert len(results) == 1
    assert results[0].episode_path == mkv.resolve()
    assert results[0].subtitle_path == ass.resolve()
    assert results[0].anime_title == "Cool Anime"
