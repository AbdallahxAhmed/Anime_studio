import pytest
from pathlib import Path
from pydantic import ValidationError

from src.models.ingestion import FontIngestionResult


def test_font_ingestion_result_valid():
    result = FontIngestionResult(
        success_count=5,
        skipped_count=2,
        failed_count=1,
        failed_details=[(Path("/fonts/corrupt.ttf"), "Zero-byte file")],
        source="manual_import",
    )
    assert result.success_count == 5
    assert result.skipped_count == 2
    assert result.failed_count == 1
    assert len(result.failed_details) == 1
    assert result.failed_details[0] == (Path("/fonts/corrupt.ttf"), "Zero-byte file")
    assert result.source == "manual_import"

    # Test serialization round-trip
    dumped = result.model_dump(mode="json")
    assert dumped["success_count"] == 5
    assert dumped["skipped_count"] == 2
    assert dumped["failed_count"] == 1
    assert dumped["failed_details"] == [["/fonts/corrupt.ttf", "Zero-byte file"]]
    assert dumped["source"] == "manual_import"


def test_font_ingestion_result_validation():
    # Negative count
    with pytest.raises(ValidationError):
        FontIngestionResult(
            success_count=-1,
            skipped_count=0,
            failed_count=0,
            failed_details=[],
            source="manual",
        )

    # Empty source
    with pytest.raises(ValidationError):
        FontIngestionResult(
            success_count=0,
            skipped_count=0,
            failed_count=0,
            failed_details=[],
            source="",
        )


def test_font_ingestion_result_frozen():
    result = FontIngestionResult(
        success_count=1,
        skipped_count=0,
        failed_count=0,
        failed_details=[],
        source="auto_discovery",
    )
    with pytest.raises(ValidationError):
        result.success_count = 2
