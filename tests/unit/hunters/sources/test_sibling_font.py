from pathlib import Path
import pytest
import shutil
from src.hunters.sources.sibling_font import SiblingFontHunter
from src.models.font import FontQuery


def test_sibling_font_hunter_supports() -> None:
    hunter = SiblingFontHunter()
    query = FontQuery(
        requested_name="TestTTF",
        anime_title="Test",
        episode_path=Path("ep1.mkv"),
    )
    assert hunter.supports(query) is True


@pytest.mark.anyio
async def test_sibling_font_hunter_finds_in_adjacent_fonts_dir(
    tmp_path: Path,
) -> None:
    episode_path = tmp_path / "ep1.mkv"
    fonts_dir = tmp_path / "Fonts"
    fonts_dir.mkdir()

    shutil.copy("tests/fixtures/fonts/valid.ttf", fonts_dir / "my_font.ttf")

    hunter = SiblingFontHunter()
    query = FontQuery(
        requested_name="TestTTF",
        anime_title="Test",
        episode_path=episode_path,
    )

    results = await hunter.search(query)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].font_asset is not None
    assert results[0].font_asset.name == "TestTTF Regular"
    assert results[0].font_asset.file_path == fonts_dir / "my_font.ttf"
    assert results[0].font_asset.is_cacheable is True

    payload = await hunter.download(results[0])
    assert payload.font_name == "TestTTF Regular"
    assert len(payload.font_data) > 0
    assert payload.file_extension == ".ttf"


@pytest.mark.anyio
async def test_sibling_font_hunter_finds_in_parent_fonts_dir(
    tmp_path: Path,
) -> None:
    anime_dir = tmp_path / "anime"
    anime_dir.mkdir()
    episode_path = anime_dir / "ep1.mkv"

    fonts_dir = tmp_path / "Fonts"
    fonts_dir.mkdir()
    shutil.copy("tests/fixtures/fonts/valid.ttf", fonts_dir / "my_font.ttf")

    hunter = SiblingFontHunter()
    query = FontQuery(
        requested_name="TestTTF",
        anime_title="Test",
        episode_path=episode_path,
    )

    results = await hunter.search(query)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].font_asset is not None
    assert results[0].font_asset.name == "TestTTF Regular"


@pytest.mark.anyio
async def test_sibling_font_hunter_no_match(tmp_path: Path) -> None:
    episode_path = tmp_path / "ep1.mkv"
    fonts_dir = tmp_path / "Fonts"
    fonts_dir.mkdir()
    shutil.copy("tests/fixtures/fonts/valid.ttf", fonts_dir / "my_font.ttf")

    hunter = SiblingFontHunter()
    query = FontQuery(
        requested_name="NonExistent",
        anime_title="Test",
        episode_path=episode_path,
    )
    results = await hunter.search(query)
    assert len(results) == 0


@pytest.mark.anyio
async def test_sibling_font_hunter_no_dir(tmp_path: Path) -> None:
    episode_path = tmp_path / "ep1.mkv"
    hunter = SiblingFontHunter()
    query = FontQuery(
        requested_name="TestTTF",
        anime_title="Test",
        episode_path=episode_path,
    )
    results = await hunter.search(query)
    assert len(results) == 0


@pytest.mark.anyio
async def test_sibling_font_hunter_rejects_corrupt(tmp_path: Path) -> None:
    episode_path = tmp_path / "ep1.mkv"
    fonts_dir = tmp_path / "Fonts"
    fonts_dir.mkdir()
    shutil.copy("tests/fixtures/fonts/corrupt.ttf", fonts_dir / "my_font.ttf")

    hunter = SiblingFontHunter()
    query = FontQuery(
        requested_name="corrupt",
        anime_title="Test",
        episode_path=episode_path,
    )
    results = await hunter.search(query)
    assert len(results) == 0
