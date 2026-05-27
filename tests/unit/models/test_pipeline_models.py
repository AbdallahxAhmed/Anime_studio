from pathlib import Path
import pytest
from pydantic import ValidationError
from src.models.pipeline import (
    LibraryScanResult,
    EpisodeContext,
    PipelineConfig,
    LibraryScanOutput,
)
from src.models.report import EpisodeStatus


def test_library_scan_result_valid():
    res = LibraryScanResult(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/anime/ep1.ass"),
        anime_title="My Anime",
    )
    assert res.episode_path == Path("/anime/ep1.mkv")
    assert res.subtitle_path == Path("/anime/ep1.ass")
    assert res.anime_title == "My Anime"

    # Immutability
    with pytest.raises(ValidationError):
        res.anime_title = "New Title"


def test_episode_context_valid():
    scan = LibraryScanResult(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/anime/ep1.ass"),
        anime_title="My Anime",
    )
    ctx = EpisodeContext(
        scan_result=scan,
        status=EpisodeStatus.COMPLETE,
    )
    assert ctx.scan_result == scan
    assert ctx.status == EpisodeStatus.COMPLETE
    assert ctx.font_queries == []
    assert ctx.resolved_fonts == []
    assert ctx.missing_fonts == []

    # Immutability
    with pytest.raises(ValidationError):
        ctx.status = EpisodeStatus.FAILED


def test_pipeline_config_valid():
    cfg = PipelineConfig(
        library_path=Path("/anime"),
        dry_run=True,
        sync_enabled=False,
    )
    assert cfg.library_path == Path("/anime")
    assert cfg.dry_run is True
    assert cfg.sync_enabled is False

    # Immutability
    with pytest.raises(ValidationError):
        cfg.dry_run = False


def test_library_scan_output_valid():
    scan1 = LibraryScanResult(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/anime/ep1.ass"),
        anime_title="My Anime",
    )
    scan2 = LibraryScanResult(
        episode_path=Path("/anime/ep2.mkv"),
        subtitle_path=Path("/anime/ep2.ass"),
        anime_title="My Anime",
    )

    # Test default font_directories
    output_default = LibraryScanOutput(episodes=[scan1, scan2])
    assert output_default.episodes == [scan1, scan2]
    assert output_default.font_directories == []

    # Test explicit font_directories
    output_explicit = LibraryScanOutput(
        episodes=[scan1],
        font_directories=[Path("/anime/Fonts"), Path("/anime/fonts2")],
    )
    assert output_explicit.episodes == [scan1]
    assert output_explicit.font_directories == [
        Path("/anime/Fonts"),
        Path("/anime/fonts2"),
    ]

    # Test frozen immutability
    with pytest.raises(ValidationError):
        output_default.font_directories = [Path("/another")]

    # Test JSON round-trip
    dumped = output_explicit.model_dump(mode="json")
    assert dumped["font_directories"] == ["/anime/Fonts", "/anime/fonts2"]
    assert dumped["episodes"][0]["episode_path"] == "/anime/ep1.mkv"
