import io
import zipfile
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.hunters.sources.dafont import DaFontHunter
from src.models.font import FontQuery


def test_dafont_hunter_supports() -> None:
    hunter = DaFontHunter()
    query = FontQuery(
        requested_name="TestTTF",
        anime_title="Test",
        episode_path=Path("ep1.mkv"),
    )
    assert hunter.supports(query) is True


@pytest.mark.anyio
async def test_dafont_hunter_success() -> None:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        with open("tests/fixtures/fonts/valid.ttf", "rb") as f:
            zf.writestr("valid.ttf", f.read())
    zip_data = zip_buffer.getvalue()

    search_html = '<div><a href="dl.php?f=test_font">Download</a></div>'

    mock_resp_search = MagicMock()
    mock_resp_search.status_code = 200
    mock_resp_search.text = search_html
    mock_resp_search.raise_for_status = MagicMock()

    mock_resp_download = MagicMock()
    mock_resp_download.status_code = 200
    mock_resp_download.content = zip_data
    mock_resp_download.raise_for_status = MagicMock()

    async def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "search.php" in url:
            return mock_resp_search
        elif "dl.php" in url:
            return mock_resp_download
        return MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get_fn:
        mock_get_fn.side_effect = mock_get

        hunter = DaFontHunter()
        query = FontQuery(
            requested_name="TestTTF",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )

        results = await hunter.search(query)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].font_asset is not None
        assert results[0].font_asset.name == "TestTTF Regular"

        # Check result cache
        mock_get_fn.reset_mock()
        results2 = await hunter.search(query)
        assert len(results2) == 1
        mock_get_fn.assert_not_called()

        payload = await hunter.download(results[0])
        assert payload.font_name == "TestTTF Regular"
        assert len(payload.font_data) > 0


@pytest.mark.anyio
async def test_dafont_hunter_no_slugs() -> None:
    mock_resp_search = MagicMock()
    mock_resp_search.status_code = 200
    mock_resp_search.text = "no links here"
    mock_resp_search.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp_search

        hunter = DaFontHunter()
        query = FontQuery(
            requested_name="TestTTF",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )

        results = await hunter.search(query)
        assert len(results) == 0
