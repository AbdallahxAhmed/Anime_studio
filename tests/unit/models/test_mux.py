from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import ValidationError

from src.models.font import FontAsset
from src.models.mux import MuxJob, MuxResult
from src.models.trash import TrashReceipt


@pytest.fixture
def sample_font_assets():
    return [
        FontAsset(
            name="Arial",
            file_path=Path("/fonts/arial.ttf"),
            source="system",
            layer_found=1,
            cache_hit=False,
            nameids={1: "Arial"},
        ),
        FontAsset(
            name="Helvetica",
            file_path=Path("/fonts/helvetica.ttf"),
            source="web",
            layer_found=4,
            cache_hit=True,
            nameids={1: "Helvetica"},
        ),
    ]


def test_mux_job_valid(sample_font_assets):
    job = MuxJob(
        episode_path=Path("/videos/ep_01.mp4"),
        subtitle_path=Path("/subs/ep_01.ass"),
        fonts=sample_font_assets,
        output_path=Path("/videos/ep_01.mkv"),
    )
    assert job.episode_path == Path("/videos/ep_01.mp4")
    assert job.dry_run is False
    assert len(job.fonts) == 2

    # Test JSON round-trip
    dumped = job.model_dump(mode="json")
    assert dumped["episode_path"] == "/videos/ep_01.mp4"
    assert dumped["dry_run"] is False
    assert len(dumped["fonts"]) == 2


def test_mux_job_plan_trash_disposal(sample_font_assets):
    job = MuxJob(
        episode_path=Path("/videos/ep_01.mp4"),
        subtitle_path=Path("/subs/ep_01.ass"),
        fonts=sample_font_assets,
        output_path=Path("/videos/ep_01.mkv"),
    )

    now = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)
    receipt = job.plan_trash_disposal(timestamp=now, max_age_days=14)

    assert isinstance(receipt, TrashReceipt)
    assert receipt.original_path == Path("/videos/ep_01.mp4")
    assert receipt.trash_path == Path(
        "/videos/.anime_studio_trash/EXP-2026-06-09-ep_01.mp4"
    )
    assert receipt.deletion_time == now
    assert receipt.expiration_time == datetime(
        2026, 6, 9, 10, 0, 0, tzinfo=timezone.utc
    )


def test_mux_job_immutability(sample_font_assets):
    job = MuxJob(
        episode_path=Path("/videos/ep_01.mp4"),
        subtitle_path=Path("/subs/ep_01.ass"),
        fonts=sample_font_assets,
        output_path=Path("/videos/ep_01.mkv"),
    )
    with pytest.raises(ValidationError):
        job.dry_run = True


def test_mux_result_valid():
    res = MuxResult(
        success=True,
        output_path=Path("/videos/ep_01.mkv"),
        duration_ms=4500.2,
        fonts_attached=2,
    )
    assert res.success is True
    assert res.warnings == []
    assert res.fonts_attached == 2

    dumped = res.model_dump(mode="json")
    assert dumped["output_path"] == "/videos/ep_01.mkv"
    assert dumped["warnings"] == []


def test_mux_result_validation():
    with pytest.raises(ValidationError):
        # negative duration_ms
        MuxResult(
            success=True,
            output_path=Path("/videos/ep_01.mkv"),
            duration_ms=-100.0,
            fonts_attached=1,
        )
    with pytest.raises(ValidationError):
        # negative fonts_attached
        MuxResult(
            success=True,
            output_path=Path("/videos/ep_01.mkv"),
            duration_ms=100.0,
            fonts_attached=-1,
        )
