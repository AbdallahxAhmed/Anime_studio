import asyncio
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from src.core.font_cache import FontCache
from src.core.font_ingestion import FontIngestionService, _extract_font_name_from_bytes
from src.models.font import FontAsset


def test_extract_font_name_from_bytes_valid_ttf():
    font_path = Path("tests/fixtures/fonts/valid.ttf")
    data = font_path.read_bytes()
    name, nameids = _extract_font_name_from_bytes(data, "fallback")
    assert name == "TestTTF Regular"
    assert nameids[1] == "TestTTF"


def test_extract_font_name_from_bytes_corrupt():
    data = b"invalid_font_data"
    with pytest.raises(ValueError, match="Failed to parse font metadata"):
        _extract_font_name_from_bytes(data, "fallback")


@pytest.fixture
def mock_cache():
    cache = MagicMock(spec=FontCache)
    cache.lookup.return_value = None
    return cache


@pytest.fixture
def semaphore():
    return asyncio.Semaphore(5)


@pytest.mark.anyio
async def test_ingest_directories_and_files(mock_cache, semaphore):
    service = FontIngestionService(mock_cache, semaphore)

    # 1. Ingest directories recursively
    # We pass the tests/fixtures/fonts directory which has valid.ttf, valid.otf, and corrupt.ttf
    with patch("structlog.get_logger") as mock_logger_cls:
        mock_logger = MagicMock()
        mock_logger_cls.return_value = mock_logger

        result = await service.ingest_directories(
            [Path("tests/fixtures/fonts")], source="auto_discovery"
        )

        assert result.success_count == 2  # valid.ttf, valid.otf
        assert result.skipped_count == 0
        assert result.failed_count == 1  # corrupt.ttf
        assert len(result.failed_details) == 1
        assert result.failed_details[0][0].name == "corrupt.ttf"
        assert "Failed to parse font metadata" in result.failed_details[0][1]

        # Verify that mock_cache.store was called exactly twice (for the two valid fonts)
        assert mock_cache.store.call_count == 2


@pytest.mark.anyio
async def test_ingest_files_deduplication(mock_cache, semaphore):
    # Lookup returns an existing asset to simulate a duplicate font (already in cache)
    mock_cache.lookup.return_value = FontAsset(
        name="TestTTF Regular",
        file_path=Path("some/path.ttf"),
        source="system",
        layer_found=0,
        cache_hit=True,
        nameids={},
    )

    service = FontIngestionService(mock_cache, semaphore)

    # Ingesting the valid.ttf file which will be matched by name
    result = await service.ingest_files(
        [Path("tests/fixtures/fonts/valid.ttf")], source="manual_import"
    )

    assert result.success_count == 0
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert len(result.failed_details) == 0

    # Store must never have been called because it was deduplicated
    mock_cache.store.assert_not_called()


@pytest.mark.anyio
async def test_ingest_directories_non_existent(mock_cache, semaphore):
    service = FontIngestionService(mock_cache, semaphore)

    result = await service.ingest_directories(
        [Path("non_existent_folder_xyz_123")], source="manual_import"
    )

    assert result.success_count == 0
    assert result.skipped_count == 0
    assert result.failed_count == 0
    assert len(result.failed_details) == 0
