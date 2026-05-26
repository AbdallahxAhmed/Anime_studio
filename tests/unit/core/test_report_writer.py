from datetime import datetime, timezone
from pathlib import Path
from src.core.report_writer import render_report, render_incremental_section
from src.models.report import PipelineReport, EpisodeReport, EpisodeStatus
from src.models.subtitle import SyncResult
from src.models.mux import MuxResult


def test_render_report_valid():
    run_time = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    ep1 = EpisodeReport(
        episode_path=Path("ep1.mkv"),
        status=EpisodeStatus.COMPLETE,
        subtitle_result=SyncResult(
            success=True,
            tool_used="alass",
            offset_ms=120.0,
            duration_ms=500.0,
        ),
        mux_result=MuxResult(
            success=True,
            output_path=Path("ep1_muxed.mkv"),
            duration_ms=1500.0,
            fonts_attached=2,
        ),
        applied_rules=["Rule 1", "Rule 2"],
    )
    ep2 = EpisodeReport(
        episode_path=Path("ep2.mkv"),
        status=EpisodeStatus.PARTIAL,
        missing_fonts=["SomeMissingFont"],
    )
    report = PipelineReport(
        run_timestamp=run_time,
        duration_ms=3500.0,
        anime_title="Awesome Show",
        episodes=[ep1, ep2],
        total_fonts_found=5,
        genuine_misses=["SomeMissingFont"],
    )

    md = render_report(report)

    assert "Awesome Show" in md
    assert "2026-05-26 12:00:00" in md
    assert "3.50s" in md
    assert "ep1.mkv" in md
    assert "✓ COMPLETE" in md
    assert "ep2.mkv" in md
    assert "⚠ PARTIAL" in md
    assert "SomeMissingFont" in md
    assert "Rule 1" in md
    assert "Rule 2" in md


def test_render_incremental_section_valid():
    run_time = datetime(2026, 5, 26, 13, 0, 0, tzinfo=timezone.utc)
    ep = EpisodeReport(
        episode_path=Path("ep3.mkv"),
        status=EpisodeStatus.SKIPPED,
    )
    report = PipelineReport(
        run_timestamp=run_time,
        duration_ms=0.0,
        anime_title="Awesome Show",
        episodes=[ep],
        total_fonts_found=0,
    )

    inc = render_incremental_section(report)
    assert "## Incremental Run: 2026-05-26 13:00:00" in inc
    assert "➖ SKIPPED" in inc
