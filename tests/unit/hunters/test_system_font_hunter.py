from pathlib import Path
from unittest.mock import patch
import pytest

from src.hunters.system_font_hunter import (
    SystemFontHunter,
    _get_system_font_dirs,
    _extract_font_names,
)
from src.models.font import FontQuery, HunterResult


def test_system_font_dirs_windows():
    with patch("sys.platform", "win32"):
        dirs = _get_system_font_dirs()
        assert len(dirs) == 2
        assert dirs[0] == Path("C:/Windows/Fonts")
        assert "AppData" in str(dirs[1])


def test_system_font_dirs_macos():
    with patch("sys.platform", "darwin"):
        dirs = _get_system_font_dirs()
        assert len(dirs) == 3
        assert dirs[1] == Path("/Library/Fonts")
        assert dirs[2] == Path("/System/Library/Fonts")


def test_system_font_dirs_linux():
    with patch("sys.platform", "linux"):
        dirs = _get_system_font_dirs()
        assert len(dirs) == 3
        assert dirs[1] == Path("/usr/local/share/fonts")
        assert dirs[2] == Path("/usr/share/fonts")


def test_extract_font_names_valid_ttf():
    font_path = Path("tests/fixtures/fonts/valid.ttf")
    primary_name, nameids, searchable_names = _extract_font_names(font_path)

    assert primary_name == "TestTTF Regular"
    assert nameids[1] == "TestTTF"
    assert nameids[4] == "TestTTF Regular"
    assert nameids[6] == "TestTTF-Regular"
    assert "testttf" in searchable_names
    assert "testttf regular" in searchable_names
    assert "testttf-regular" in searchable_names


def test_extract_font_names_valid_otf():
    font_path = Path("tests/fixtures/fonts/valid.otf")
    primary_name, nameids, searchable_names = _extract_font_names(font_path)

    assert primary_name == "TestOTF Regular"
    assert nameids[1] == "TestOTF"
    assert nameids[4] == "TestOTF Regular"
    assert nameids[6] == "TestOTF-Regular"
    assert "testotf" in searchable_names
    assert "testotf regular" in searchable_names
    assert "testotf-regular" in searchable_names


def test_extract_font_names_corrupt_ttf():
    font_path = Path("tests/fixtures/fonts/corrupt.ttf")
    primary_name, nameids, searchable_names = _extract_font_names(font_path)

    assert primary_name == "corrupt"
    assert nameids == {}
    assert searchable_names == set()


def test_system_font_hunter_supports():
    hunter = SystemFontHunter()
    query = FontQuery(
        requested_name="Arial", anime_title="Test", episode_path=Path("ep1.mkv")
    )
    assert hunter.supports(query) is True


@pytest.mark.anyio
async def test_system_font_hunter_search_match_and_miss():
    hunter = SystemFontHunter()

    # Mock _get_system_font_dirs to return our fixtures folder
    with patch("src.hunters.system_font_hunter._get_system_font_dirs") as mock_dirs:
        mock_dirs.return_value = [Path("tests/fixtures/fonts")]

        # Query for TTF font family name
        query_ttf = FontQuery(
            requested_name="TestTTF",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )
        results = await hunter.search(query_ttf)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].font_asset is not None
        assert results[0].font_asset.name == "TestTTF Regular"
        assert results[0].font_asset.is_cacheable is False
        assert results[0].font_asset.source == "system"
        assert results[0].font_asset.layer_found == 4
        assert results[0].font_asset.file_path == Path("tests/fixtures/fonts/valid.ttf")

        # Query for OTF full name
        query_otf = FontQuery(
            requested_name="TestOTF Regular",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )
        results_otf = await hunter.search(query_otf)
        assert len(results_otf) == 1
        assert results_otf[0].success is True
        assert results_otf[0].font_asset.name == "TestOTF Regular"
        assert results_otf[0].font_asset.file_path == Path(
            "tests/fixtures/fonts/valid.otf"
        )

        # Query for a non-existent font (miss)
        query_miss = FontQuery(
            requested_name="NonExistentFont",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )
        results_miss = await hunter.search(query_miss)
        assert len(results_miss) == 0


@pytest.mark.anyio
async def test_system_font_hunter_download_not_implemented():
    hunter = SystemFontHunter()
    query = FontQuery(
        requested_name="Arial", anime_title="Test", episode_path=Path("ep1.mkv")
    )
    result = HunterResult(
        query=query,
        success=True,
        hunter_name=hunter.name,
        duration_ms=1.0,
        attempts=1,
    )
    with pytest.raises(NotImplementedError):
        await hunter.download(result)
