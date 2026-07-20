import io
import zipfile
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.hunters.sources.search_engine import SearchEngineHunter, is_blocked
from src.models.font import FontQuery


def test_search_engine_hunter_supports() -> None:
    hunter = SearchEngineHunter()
    query = FontQuery(
        requested_name="TestTTF",
        anime_title="Test",
        episode_path=Path("ep1.mkv"),
    )
    assert hunter.supports(query) is True


def test_is_blocked() -> None:
    assert is_blocked("https://pinterest.com/pin/1") is True
    assert is_blocked("https://www.pinterest.com/pin/1") is True
    assert is_blocked("https://facebook.com/somepage") is True
    assert is_blocked("https://example.com/somepage") is False


@pytest.mark.anyio
async def test_search_engine_hunter_success_direct() -> None:
    with open("tests/fixtures/fonts/valid.ttf", "rb") as f:
        font_data = f.read()

    ddg_html = '<div><a href="/html/?uddg=https%3A%2F%2Fexample.com%2Ffont-page">Link</a></div>'
    page_html = (
        '<div><a href="https://example.com/download/myfont.ttf">Download TTF</a></div>'
    )

    mock_resp_ddg = MagicMock()
    mock_resp_ddg.status_code = 200
    mock_resp_ddg.text = ddg_html
    mock_resp_ddg.raise_for_status = MagicMock()

    mock_resp_page = MagicMock()
    mock_resp_page.status_code = 200
    mock_resp_page.text = page_html
    mock_resp_page.raise_for_status = MagicMock()

    mock_resp_download = MagicMock()
    mock_resp_download.status_code = 200
    mock_resp_download.content = font_data
    mock_resp_download.raise_for_status = MagicMock()

    async def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "duckduckgo.com" in url:
            return mock_resp_ddg
        elif "font-page" in url:
            return mock_resp_page
        elif "myfont.ttf" in url:
            return mock_resp_download
        return MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get_fn:
        mock_get_fn.side_effect = mock_get

        hunter = SearchEngineHunter()
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
async def test_search_engine_hunter_success_zip() -> None:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        with open("tests/fixtures/fonts/valid.ttf", "rb") as f:
            zf.writestr("valid.ttf", f.read())
    zip_data = zip_buffer.getvalue()

    ddg_html = '<div><a href="/html/?uddg=https%3A%2F%2Fexample.com%2Ffont-page">Link</a></div>'
    page_html = (
        '<div><a href="https://example.com/download/myfont.zip">Download ZIP</a></div>'
    )

    mock_resp_ddg = MagicMock()
    mock_resp_ddg.status_code = 200
    mock_resp_ddg.text = ddg_html
    mock_resp_ddg.raise_for_status = MagicMock()

    mock_resp_page = MagicMock()
    mock_resp_page.status_code = 200
    mock_resp_page.text = page_html
    mock_resp_page.raise_for_status = MagicMock()

    mock_resp_download = MagicMock()
    mock_resp_download.status_code = 200
    mock_resp_download.content = zip_data
    mock_resp_download.raise_for_status = MagicMock()

    async def mock_get(url: str, **kwargs: any) -> MagicMock:
        if "duckduckgo.com" in url:
            return mock_resp_ddg
        elif "font-page" in url:
            return mock_resp_page
        elif "myfont.zip" in url:
            return mock_resp_download
        return MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get_fn:
        mock_get_fn.side_effect = mock_get

        hunter = SearchEngineHunter()
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

        payload = await hunter.download(results[0])
        assert payload.font_name == "TestTTF Regular"
        assert len(payload.font_data) > 0


@pytest.mark.anyio
async def test_search_engine_hunter_no_results() -> None:
    mock_resp_ddg = MagicMock()
    mock_resp_ddg.status_code = 200
    mock_resp_ddg.text = "no links here"
    mock_resp_ddg.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp_ddg

        hunter = SearchEngineHunter()
        query = FontQuery(
            requested_name="TestTTF",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )

        results = await hunter.search(query)
        assert len(results) == 0
