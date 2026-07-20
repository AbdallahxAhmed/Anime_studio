import io
import zipfile
from pathlib import Path
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from src.hunters.sources.google_fonts import GoogleFontsHunter
from src.models.font import FontQuery


def test_google_fonts_hunter_supports() -> None:
    hunter = GoogleFontsHunter()
    query = FontQuery(
        requested_name="TestTTF",
        anime_title="Test",
        episode_path=Path("ep1.mkv"),
    )
    assert hunter.supports(query) is True


@pytest.mark.anyio
async def test_google_fonts_hunter_success() -> None:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        with open("tests/fixtures/fonts/valid.ttf", "rb") as f:
            zf.writestr("valid.ttf", f.read())
    zip_data = zip_buffer.getvalue()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = zip_data
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        hunter = GoogleFontsHunter(proxy="socks5://localhost:1080")
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
async def test_google_fonts_hunter_404() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        hunter = GoogleFontsHunter()
        query = FontQuery(
            requested_name="NonExistent",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )

        results = await hunter.search(query)
        assert len(results) == 0


@pytest.mark.anyio
async def test_google_fonts_hunter_corrupt_zip() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"invalid zip data"
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        hunter = GoogleFontsHunter()
        query = FontQuery(
            requested_name="TestTTF",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )

        results = await hunter.search(query)
        assert len(results) == 0


@pytest.mark.anyio
async def test_google_fonts_hunter_timeout() -> None:
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("timeout")

        hunter = GoogleFontsHunter()
        query = FontQuery(
            requested_name="TestTTF",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )

        with pytest.raises(httpx.TimeoutException):
            await hunter.search(query)


@pytest.mark.anyio
async def test_google_fonts_hunter_proxy() -> None:
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b""
    mock_client.get.return_value = mock_resp

    with patch("httpx.AsyncClient", return_value=mock_client) as mock_client_class:
        mock_client.__aenter__.return_value = mock_client

        hunter = GoogleFontsHunter(proxy="http://127.0.0.1:8888")
        query = FontQuery(
            requested_name="TestTTF",
            anime_title="Test",
            episode_path=Path("ep1.mkv"),
        )
        try:
            await hunter.search(query)
        except Exception:
            pass

        mock_client_class.assert_called_once()
        kwargs = mock_client_class.call_args[1]
        assert kwargs.get("proxy") == "http://127.0.0.1:8888"
