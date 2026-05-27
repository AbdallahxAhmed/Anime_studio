from src.gui.messages import ErrorInfo, EpisodeResult, EpisodeStatus, PipelineRunResult


def test_error_info_creation() -> None:
    """Verify that ErrorInfo attributes are correctly set."""
    err = ErrorInfo(message="Test error", detail="Detailed info", is_critical=True)
    assert err.message == "Test error"
    assert err.detail == "Detailed info"
    assert err.is_critical is True


def test_episode_result_creation() -> None:
    """Verify EpisodeResult fields."""
    res = EpisodeResult(
        name="Ep 01.mkv",
        status=EpisodeStatus.COMPLETE,
        fonts_found=5,
        fonts_missing=0,
        error_summary="All matched"
    )
    assert res.name == "Ep 01.mkv"
    assert res.status == EpisodeStatus.COMPLETE
    assert res.fonts_found == 5
    assert res.fonts_missing == 0
    assert res.error_summary == "All matched"


def test_pipeline_run_result_creation() -> None:
    """Verify PipelineRunResult fields."""
    ep_res = EpisodeResult(
        name="Ep 01.mkv",
        status=EpisodeStatus.COMPLETE,
        fonts_found=3,
        fonts_missing=1
    )
    run_res = PipelineRunResult(
        episodes=[ep_res],
        total_duration_seconds=12.5,
        report_path="/path/to/report.md",
        total_fonts_found=3,
        total_fonts_missing=1,
        dry_run=False
    )
    assert len(run_res.episodes) == 1
    assert run_res.total_duration_seconds == 12.5
    assert run_res.report_path == "/path/to/report.md"
    assert run_res.total_fonts_found == 3
    assert run_res.total_fonts_missing == 1
    assert run_res.dry_run is False
