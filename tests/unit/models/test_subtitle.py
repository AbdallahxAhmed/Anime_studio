from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import ValidationError

from src.models.subtitle import SubtitleFile, SyncResult, AssetLifecycle
from src.models.trash import TrashReceipt


def test_asset_lifecycle_enum():
    assert AssetLifecycle.ORIGINAL == "ORIGINAL"
    assert AssetLifecycle.REPAIRED == "REPAIRED"
    assert AssetLifecycle.SYNCED == "SYNCED"
    assert AssetLifecycle.TRASHED == "TRASHED"


def test_subtitle_file_valid():
    sub = SubtitleFile(
        path=Path("/subs/episode_01.ass"),
        encoding_detected="utf-8",
        encoding_source="charset_normalizer",
        line_ending="\n",
        fonts_required=["Arial", "Helvetica"],
    )
    assert sub.path == Path("/subs/episode_01.ass")
    assert sub.lifecycle == AssetLifecycle.ORIGINAL
    assert sub.fonts_required == ["Arial", "Helvetica"]

    # Test JSON round-trip
    dumped = sub.model_dump(mode="json")
    assert dumped["path"] == "/subs/episode_01.ass"
    assert dumped["lifecycle"] == "ORIGINAL"


def test_subtitle_file_plan_trash_disposal():
    sub = SubtitleFile(
        path=Path("/subs/episode_01.ass"),
        encoding_detected="utf-8",
        encoding_source="charset_normalizer",
        line_ending="\n",
        fonts_required=["Arial"],
    )

    now = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)
    receipt = sub.plan_trash_disposal(timestamp=now, max_age_days=7)

    assert isinstance(receipt, TrashReceipt)
    assert receipt.original_path == Path("/subs/episode_01.ass")
    assert receipt.trash_path == Path(
        "/subs/.anime_studio_trash/EXP-2026-06-02-episode_01.ass"
    )
    assert receipt.deletion_time == now
    assert receipt.expiration_time == datetime(
        2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc
    )


def test_subtitle_file_immutability():
    sub = SubtitleFile(
        path=Path("/subs/episode_01.ass"),
        encoding_detected="utf-8",
        encoding_source="charset_normalizer",
        line_ending="\n",
        fonts_required=[],
    )
    with pytest.raises(ValidationError):
        sub.encoding_detected = "utf-16"


def test_sync_result_valid():
    res = SyncResult(
        success=True,
        tool_used="alass",
        offset_ms=-150.0,
        duration_ms=1250.5,
    )
    assert res.success is True
    assert res.tool_fallback_used is None
    assert res.duration_ms == 1250.5

    dumped = res.model_dump(mode="json")
    assert dumped["tool_fallback_used"] is None


def test_sync_result_validation():
    with pytest.raises(ValidationError):
        # negative duration_ms
        SyncResult(
            success=True,
            tool_used="alass",
            offset_ms=0.0,
            duration_ms=-1.0,
        )
