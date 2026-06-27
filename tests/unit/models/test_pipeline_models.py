from pathlib import Path
import pytest
from pydantic import ValidationError
from src.models.pipeline import (
    LibraryScanResult,
    EpisodeContext,
    PipelineConfig,
    LibraryScanOutput,
    SubFolderNode,
    ShowNode,
    ShowStatus,
    ShowSummary,
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
    assert output_default.show_tree == ()

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


def test_sub_folder_node_and_show_node():
    scan = LibraryScanResult(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/anime/ep1.ass"),
        anime_title="My Anime",
    )
    ctx = EpisodeContext(
        scan_result=scan,
        status=EpisodeStatus.COMPLETE,
    )
    sf = SubFolderNode(
        name="Season 1",
        path=Path("/anime/Season 1"),
        episodes=(ctx,),
    )
    assert sf.name == "Season 1"
    assert sf.path == Path("/anime/Season 1")
    assert sf.episodes == (ctx,)
    assert sf.total_count == 1

    # ShowNode
    show = ShowNode(
        name="My Anime",
        path=Path("/anime"),
        sub_folders=(sf,),
        episodes=(ctx,),
    )
    assert show.name == "My Anime"
    assert show.path == Path("/anime")
    assert show.sub_folders == (sf,)
    assert show.episodes == (ctx,)
    assert show.total_count == 2  # 1 direct + 1 from sub_folder

    # Immutability
    with pytest.raises(AttributeError):
        sf.name = "Season 2"
    with pytest.raises(AttributeError):
        show.name = "New Show"


def test_pipeline_config_selected_paths():
    cfg = PipelineConfig(
        library_path=Path("/anime"),
        selected_paths=frozenset({Path("/anime/Season 1")}),
    )
    assert cfg.selected_paths == frozenset({Path("/anime/Season 1")})

    # Default is None
    cfg_default = PipelineConfig(library_path=Path("/anime"))
    assert cfg_default.selected_paths is None


def test_library_scan_output_show_tree():
    output = LibraryScanOutput(
        episodes=[],
        show_tree=()
    )
    assert output.show_tree == ()


def test_show_status_and_summary():
    # Test ShowStatus values
    assert ShowStatus.PENDING == "pending"
    assert ShowStatus.PROCESSING == "processing"
    assert ShowStatus.READY == "ready"
    assert ShowStatus.ALL_DONE == "all_done"
    assert ShowStatus.NO_SUBTITLE == "no_subtitle"
    assert ShowStatus.WARNING == "warning"

    # Test ShowSummary construction
    summary = ShowSummary(
        name="Hunter x Hunter",
        path=Path("/anime/Hunter x Hunter"),
        status=ShowStatus.READY,
        episode_count=148,
        processed_count=0,
        subtitle_text="148 ready / 0 processed",
    )
    assert summary.name == "Hunter x Hunter"
    assert summary.path == Path("/anime/Hunter x Hunter")
    assert summary.status == ShowStatus.READY
    assert summary.episode_count == 148
    assert summary.processed_count == 0
    assert summary.subtitle_text == "148 ready / 0 processed"

    # Test frozen immutability
    with pytest.raises(AttributeError):
        summary.status = ShowStatus.ALL_DONE
