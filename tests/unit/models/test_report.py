from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import ValidationError

from src.models.subtitle import SyncResult
from src.models.mux import MuxResult
from src.models.report import EpisodeStatus, EpisodeReport, PipelineReport


def test_episode_status_enum():
    assert EpisodeStatus.COMPLETE == "complete"
    assert EpisodeStatus.PARTIAL == "partial"
    assert EpisodeStatus.FAILED == "failed"
    assert EpisodeStatus.SKIPPED == "skipped"


def test_episode_report_valid():
    rep = EpisodeReport(
        episode_path=Path("/videos/ep_01.mp4"),
        status=EpisodeStatus.COMPLETE,
        subtitle_result=SyncResult(
            success=True,
            tool_used="alass",
            offset_ms=0.0,
            duration_ms=500.0,
        ),
        mux_result=MuxResult(
            success=True,
            output_path=Path("/videos/ep_01.mkv"),
            duration_ms=1000.0,
            fonts_attached=2,
        ),
        missing_fonts=[],
        applied_rules=["rule_1"],
    )
    assert rep.status == EpisodeStatus.COMPLETE
    assert rep.applied_rules == ["rule_1"]

    # Test default values
    rep_min = EpisodeReport(
        episode_path=Path("/videos/ep_02.mp4"),
        status=EpisodeStatus.FAILED,
    )
    assert rep_min.subtitle_result is None
    assert rep_min.mux_result is None
    assert rep_min.missing_fonts == []
    assert rep_min.applied_rules == []


def test_episode_report_immutability():
    rep = EpisodeReport(
        episode_path=Path("/videos/ep_01.mp4"),
        status=EpisodeStatus.COMPLETE,
    )
    with pytest.raises(ValidationError):
        rep.status = EpisodeStatus.FAILED


def test_pipeline_report_valid():
    episodes = [
        EpisodeReport(episode_path=Path("ep1.mp4"), status=EpisodeStatus.COMPLETE),
        EpisodeReport(episode_path=Path("ep2.mp4"), status=EpisodeStatus.FAILED),
    ]
    now = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)

    report = PipelineReport(
        run_timestamp=now,
        duration_ms=12500.0,
        anime_title="Test Anime",
        episodes=episodes,
        total_fonts_found=10,
        genuine_misses=["FontA"],
    )

    assert report.total_fonts_found == 10
    assert len(report.episodes) == 2

    # Test JSON round-trip
    dumped = report.model_dump(mode="json")
    assert dumped["run_timestamp"] == "2026-05-26T10:00:00Z"
    assert len(dumped["episodes"]) == 2


def test_pipeline_report_validation():
    episodes = []
    now = datetime.now()
    with pytest.raises(ValidationError):
        # negative duration_ms
        PipelineReport(
            run_timestamp=now,
            duration_ms=-1.0,
            anime_title="Test",
            episodes=episodes,
            total_fonts_found=0,
        )
    with pytest.raises(ValidationError):
        # negative total_fonts_found
        PipelineReport(
            run_timestamp=now,
            duration_ms=0.0,
            anime_title="Test",
            episodes=episodes,
            total_fonts_found=-1,
        )
