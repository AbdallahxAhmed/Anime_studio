import asyncio
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core import pipeline_runner as pipeline_runner_module
from src.core.pipeline_runner import PipelineRunner
from src.core.font_resolver import FontResolver
from src.core.library_scanner import LibraryScanner
from src.ports.subprocess import SubprocessPort
from src.ports.filesystem import FilesystemPort
from src.adapters.dependency_checker import ToolRegistry
from src.config import AppConfig
from src.models.pipeline import (
    EpisodeContext,
    LibraryScanResult,
    PipelineConfig,
    LibraryScanOutput,
)
from src.models.report import EpisodeStatus
from src.models.font import FontAsset
from src.models.tool_result import ToolResult
from src.core.font_ingestion import FontIngestionService
from src.errors import PipelineStoppedError


@pytest.fixture
def mock_font_resolver():
    resolver = MagicMock(spec=FontResolver)

    async def _mock_resolve(query):
        return FontAsset(
            name=query.requested_name,
            file_path=Path("/fonts") / f"{query.requested_name}.ttf",
            source="mock_hunter",
            layer_found=1,
            cache_hit=True,
            nameids={},
        )

    resolver.resolve = AsyncMock(side_effect=_mock_resolve)
    # PipelineRunner creates an immutable run-local resolver so discovery scope
    # cannot leak between selected-show runs.  Keep this test double local too.
    resolver.for_run.return_value = resolver
    return resolver


@pytest.fixture
def mock_subprocess():
    sub = MagicMock(spec=SubprocessPort)
    sub.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="mock",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=10.0,
        )
    )
    return sub


@pytest.fixture
def mock_filesystem():
    fs = MagicMock(spec=FilesystemPort)
    fs.move_to_trash = AsyncMock()
    fs.write_file_atomic = AsyncMock()
    fs.ensure_directory = AsyncMock()
    fs.replace_file = AsyncMock()
    return fs


@pytest.fixture
def mock_tool_registry():
    reg = MagicMock(spec=ToolRegistry)
    reg.is_available.return_value = True
    return reg


@pytest.fixture
def mock_font_ingestion_service():
    service = MagicMock(spec=FontIngestionService)
    service.ingest_directories = AsyncMock()
    service.ingest_files = AsyncMock()
    return service


@pytest.fixture
def disk_semaphore():
    return asyncio.Semaphore(2)


@pytest.fixture
def app_config():
    return AppConfig(max_concurrent_disk_io=2)


def _make_mock_scanner(scan_output: LibraryScanOutput) -> LibraryScanner:
    """Create a mock LibraryScanner that returns the given output."""
    scanner = MagicMock(spec=LibraryScanner)
    scanner.scan = AsyncMock(return_value=scan_output)
    return scanner


def _make_runner(
    scan_output,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
) -> PipelineRunner:
    return PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=_make_mock_scanner(scan_output),
    )


def _single_episode_output(
    tmp_path: Path, episode_name: str = "episode"
) -> tuple[LibraryScanOutput, LibraryScanResult]:
    """Create fake empty media plus a real, valid subtitle for runner tests."""
    episode_path = tmp_path / f"{episode_name}.mkv"
    subtitle_path = tmp_path / f"{episode_name}.ass"
    episode_path.touch()
    subtitle_path.write_text(
        "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial",
        encoding="utf-8",
    )
    scan = LibraryScanResult(
        episode_path=episode_path,
        subtitle_path=subtitle_path,
        anime_title="Show",
    )
    return LibraryScanOutput(episodes=[scan], font_directories=[]), scan


@pytest.mark.anyio
async def test_pipeline_runner_empty_library(
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=[], font_directories=[])
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    cfg = PipelineConfig(library_path=Path("/empty"))
    report = await runner.run(cfg)

    assert report.total_fonts_found == 0
    assert len(report.episodes) == 0
    mock_filesystem.write_file_atomic.assert_called_once()
    # Ingestion shouldn't be called since there are no directories
    mock_font_ingestion_service.ingest_directories.assert_not_called()


@pytest.mark.anyio
async def test_pipeline_runner_success(
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_res = [
        LibraryScanResult(
            episode_path=Path("/anime/cool_show_01.mkv"),
            subtitle_path=Path("/anime/cool_show_01.ass"),
            anime_title="Cool Show",
        )
    ]
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=scan_res, font_directories=[Path("/anime/Fonts")])
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    repaired_content = "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial"

    with patch(
        "src.core.pipeline_runner.repair_ass",
        MagicMock(return_value=repaired_content),
    ):
        cfg = PipelineConfig(library_path=Path("/anime"), dry_run=False)
        report = await runner.run(cfg)

        assert len(report.episodes) == 1
        assert report.episodes[0].status == EpisodeStatus.COMPLETE
        assert report.total_fonts_found == 1
        mock_filesystem.move_to_trash.assert_called()
        mock_filesystem.replace_file.assert_called_once()

        # Ingestion MUST have been called as a pre-pipeline step
        mock_font_ingestion_service.ingest_directories.assert_called_once_with(
            [Path("/anime/Fonts")], source="auto_discovery"
        )


@pytest.mark.anyio
async def test_pipeline_runner_subtitle_sync_fallback(
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_res = [
        LibraryScanResult(
            episode_path=Path("/anime/ep1.mkv"),
            subtitle_path=Path("/anime/ep1.ass"),
            anime_title="Show",
        )
    ]
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=scan_res, font_directories=[])
    )
    # Setup runner
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    repaired_content = "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial"

    # Setup subprocess execution to simulate alass failure and ffsubsync success
    # For alass: fail (exit_code 1), for ffsubsync: success (exit_code 0)
    async def mock_execute(args, timeout=None):
        if "alass" in args[0]:
            return ToolResult(
                tool_name="alass",
                success=False,
                exit_code=1,
                stdout="alass failure",
                stderr="alass failure",
                duration_ms=50.0,
            )
        elif "ffsubsync" in args[0]:
            return ToolResult(
                tool_name="ffsubsync",
                success=True,
                exit_code=0,
                stdout="ffsubsync success: shift of 0.15s applied",
                stderr="",
                duration_ms=60.0,
            )
        return ToolResult(
            tool_name="mock",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=10.0,
        )

    mock_subprocess.execute.side_effect = mock_execute

    with (
        patch(
            "src.core.pipeline_runner.repair_ass",
            MagicMock(return_value=repaired_content),
        ),
        patch("builtins.open", MagicMock()),
    ):
        cfg = PipelineConfig(library_path=Path("/anime"), sync_enabled=True)
        report = await runner.run(cfg)

        assert len(report.episodes) == 1
        ep = report.episodes[0]
        assert ep.subtitle_result is not None
        assert ep.subtitle_result.success is True
        assert ep.subtitle_result.tool_used == "alass"
        assert ep.subtitle_result.tool_fallback_used == "ffsubsync"
        assert ep.subtitle_result.offset_ms == 150.0  # 0.15s * 1000


@pytest.mark.anyio
async def test_pipeline_runner_respects_selected_paths(
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_res = [
        LibraryScanResult(
            episode_path=Path("/anime/Show A/episode_01.mkv"),
            subtitle_path=Path("/anime/Show A/episode_01.ass"),
            anime_title="Show A",
        ),
        LibraryScanResult(
            episode_path=Path("/anime/Show B/episode_02.mkv"),
            subtitle_path=Path("/anime/Show B/episode_02.ass"),
            anime_title="Show B",
        ),
    ]
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=scan_res, font_directories=[])
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    repaired_content = "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial"

    with patch(
        "src.core.pipeline_runner.repair_ass",
        MagicMock(return_value=repaired_content),
    ):
        cfg = PipelineConfig(
            library_path=Path("/anime"),
            selected_paths=frozenset({Path("/anime/Show A/episode_01.mkv")}),
        )
        report = await runner.run(cfg)

        # Show A is processed. Show B is not in report because /anime is a mock path and has no files on disk.
        processed = [e for e in report.episodes if e.status != EpisodeStatus.SKIPPED]
        assert len(processed) == 1
        assert processed[0].episode_path == Path("/anime/Show A/episode_01.mkv")


@pytest.mark.anyio
async def test_pipeline_runner_scopes_discovery_and_skipped_accounting(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    library_root = tmp_path / "Anime"
    show_a = library_root / "ShowA"
    show_b = library_root / "ShowB"
    show_a.mkdir(parents=True)
    show_b.mkdir()
    selected_mkv = show_a / "episode_01.mkv"
    selected_ass = show_a / "episode_01.ass"
    unselected_mkv = show_a / "episode_02.mkv"
    unselected_ass = show_a / "episode_02.ass"
    duplicate_mkv = show_b / "episode_01.mkv"
    for path in (
        selected_mkv,
        selected_ass,
        unselected_mkv,
        unselected_ass,
        duplicate_mkv,
    ):
        path.touch()

    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(
            episodes=[
                LibraryScanResult(
                    episode_path=selected_mkv,
                    subtitle_path=selected_ass,
                    anime_title="Show A",
                ),
                LibraryScanResult(
                    episode_path=unselected_mkv,
                    subtitle_path=unselected_ass,
                    anime_title="Show A",
                ),
                LibraryScanResult(
                    episode_path=duplicate_mkv,
                    subtitle_path=None,
                    anime_title="Show B",
                ),
            ],
            font_directories=[],
        )
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    with patch(
        "src.core.pipeline_runner.repair_ass",
        MagicMock(
            return_value="[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial"
        ),
    ):
        report = await runner.run(
            PipelineConfig(
                library_path=library_root,
                discovery_root=show_a,
                anime_title="Show A Display Name",
                dry_run=True,
                selected_paths=frozenset({selected_mkv}),
            )
        )

    mock_scanner.scan.assert_awaited_once_with(show_a.resolve())
    assert report.anime_title == "Show A Display Name"
    assert {episode.episode_path for episode in report.episodes} == {
        selected_mkv.resolve(),
        unselected_mkv.resolve(),
    }
    assert duplicate_mkv.resolve() not in {
        episode.episode_path for episode in report.episodes
    }
    assert mock_filesystem.write_file_atomic.await_args.args[0] == (
        library_root / "_AnimeStudio_Report.md"
    )


@pytest.mark.anyio
async def test_pipeline_runner_empty_selected_paths_produces_empty_scoped_report(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    library_root = tmp_path / "Anime"
    discovery_root = library_root / "Ranma"
    discovery_root.mkdir(parents=True)
    scan_result = LibraryScanResult(
        episode_path=discovery_root / "episode_01.mkv",
        subtitle_path=discovery_root / "episode_01.ass",
        anime_title="Ranma",
    )
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=[scan_result], font_directories=[])
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    report = await runner.run(
        PipelineConfig(
            library_path=library_root,
            discovery_root=discovery_root,
            anime_title="Ranma Display Name",
            selected_paths=frozenset(),
        )
    )

    assert report.episodes == []
    assert report.anime_title == "Ranma Display Name"


@pytest.mark.anyio
async def test_pipeline_runner_uses_library_root_without_discovery_root(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    library_root = tmp_path / "Anime"
    library_root.mkdir()
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=[], font_directories=[])
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    report = await runner.run(PipelineConfig(library_path=library_root))

    mock_scanner.scan.assert_awaited_once_with(library_root.resolve())
    assert report.anime_title == "Anime"


@pytest.mark.skipif(os.name != "nt", reason="Windows path identity behavior")
@pytest.mark.anyio
async def test_pipeline_runner_matches_case_equivalent_windows_selected_path(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    library_root = tmp_path / "Anime"
    show_root = library_root / "ShowA"
    show_root.mkdir(parents=True)
    episode_path = show_root / "episode_01.mkv"
    subtitle_path = show_root / "episode_01.ass"
    episode_path.touch()
    subtitle_path.touch()
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(
            episodes=[
                LibraryScanResult(
                    episode_path=episode_path,
                    subtitle_path=subtitle_path,
                    anime_title="Show A",
                )
            ],
            font_directories=[],
        )
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    with patch(
        "src.core.pipeline_runner.repair_ass",
        MagicMock(
            return_value="[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial"
        ),
    ):
        report = await runner.run(
            PipelineConfig(
                library_path=library_root,
                discovery_root=show_root,
                dry_run=True,
                selected_paths=frozenset({Path(str(episode_path).upper())}),
            )
        )

    assert [episode.episode_path for episode in report.episodes] == [
        episode_path.resolve()
    ]


@pytest.mark.anyio
async def test_pipeline_runner_stop_event_stops_before_scan(
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_res = [
        LibraryScanResult(
            episode_path=Path("/anime/Show A/ep1.mkv"),
            subtitle_path=Path("/anime/Show A/ep1.ass"),
            anime_title="Show A",
        ),
        LibraryScanResult(
            episode_path=Path("/anime/Show A/ep2.mkv"),
            subtitle_path=Path("/anime/Show A/ep2.ass"),
            anime_title="Show A",
        ),
    ]
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=scan_res, font_directories=[])
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    stop_event = asyncio.Event()
    # Set the stop event immediately
    stop_event.set()

    cfg = PipelineConfig(library_path=Path("/anime"))
    with pytest.raises(PipelineStoppedError):
        await runner.run(cfg, stop_event=stop_event)

    mock_scanner.scan.assert_not_called()
    mock_filesystem.write_file_atomic.assert_not_called()
    mock_font_ingestion_service.ingest_directories.assert_not_called()


@pytest.mark.anyio
async def test_pipeline_runner_discards_scan_when_stop_arrives_after_scan(
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    stop_event = asyncio.Event()
    scan_output = LibraryScanOutput(episodes=[], font_directories=[Path("/fonts")])

    async def scan_then_stop(*_args, **_kwargs):
        stop_event.set()
        return scan_output

    mock_scanner = MagicMock(spec=LibraryScanner)
    mock_scanner.scan = AsyncMock(side_effect=scan_then_stop)
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    with pytest.raises(PipelineStoppedError):
        await runner.run(
            PipelineConfig(library_path=Path("/anime")), stop_event=stop_event
        )

    mock_font_ingestion_service.ingest_directories.assert_not_called()
    mock_filesystem.write_file_atomic.assert_not_called()


@pytest.mark.anyio
async def test_pipeline_runner_stop_before_mux_skips_success_artifacts(
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    """Stopping after analysis prevents muxing and all completion artifacts."""
    scan = LibraryScanResult(
        episode_path=Path("/anime/Show/episode.mkv"),
        subtitle_path=Path("/anime/Show/episode.ass"),
        anime_title="Show",
    )
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=[scan], font_directories=[])
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )
    stop_event = asyncio.Event()

    async def analyze_then_stop(*_args, **_kwargs):
        stop_event.set()
        return EpisodeContext(scan_result=scan)

    runner._analyze_episode = AsyncMock(side_effect=analyze_then_stop)
    checkpoint_manager = MagicMock()
    checkpoint_manager.load = AsyncMock(return_value=None)
    checkpoint_manager.save = AsyncMock()
    checkpoint_manager.clear = AsyncMock()
    undo_service = MagicMock()
    undo_service.save_manifest = AsyncMock()

    with pytest.raises(PipelineStoppedError):
        await runner.run(
            PipelineConfig(library_path=Path("/anime")),
            stop_event=stop_event,
            checkpoint_manager=checkpoint_manager,
            undo_service=undo_service,
        )

    mock_filesystem.write_file_atomic.assert_not_called()
    checkpoint_manager.save.assert_not_called()
    checkpoint_manager.clear.assert_not_called()
    undo_service.save_manifest.assert_not_called()


@pytest.mark.anyio
async def test_pipeline_runner_writes_manifest_and_clears_checkpoint(
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_res = [
        LibraryScanResult(
            episode_path=Path("/anime/Show A/ep1.mkv"),
            subtitle_path=Path("/anime/Show A/ep1.ass"),
            anime_title="Show A",
        ),
    ]
    mock_scanner = _make_mock_scanner(
        LibraryScanOutput(episodes=scan_res, font_directories=[])
    )
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
        font_ingestion_service=mock_font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=mock_scanner,
    )

    mock_checkpoint_manager = MagicMock()
    mock_checkpoint_manager.load = AsyncMock(return_value=None)
    mock_checkpoint_manager.save = AsyncMock()
    mock_checkpoint_manager.clear = AsyncMock()

    mock_undo_service = MagicMock()
    mock_undo_service.save_manifest = AsyncMock()
    mock_undo_service.create_manifest_id = MagicMock(return_value="id-123")

    repaired_content = "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial"
    with patch(
        "src.core.pipeline_runner.repair_ass", MagicMock(return_value=repaired_content)
    ):
        cfg = PipelineConfig(library_path=Path("/anime"))
        await runner.run(
            cfg,
            checkpoint_manager=mock_checkpoint_manager,
            undo_service=mock_undo_service,
        )

        # Verify rolling save called during the loop
        mock_checkpoint_manager.save.assert_called_once()
        # Verify manifest written
        mock_undo_service.save_manifest.assert_called_once()
        # Verify checkpoint cleared at the end
        mock_checkpoint_manager.clear.assert_called_once()


@pytest.mark.anyio
async def test_pipeline_runner_stops_during_skipped_mkv_enumeration(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    """A Stop processed by the loop interrupts a blocked directory listing."""
    scan_output, _ = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    listing_started = asyncio.Event()
    release_listing = threading.Event()
    loop = asyncio.get_running_loop()
    original_list_entries = pipeline_runner_module._list_directory_entries

    def list_after_release(directory: Path):
        loop.call_soon_threadsafe(listing_started.set)
        release_listing.wait()
        return original_list_entries(directory)

    with patch(
        "src.core.pipeline_runner._list_directory_entries",
        side_effect=list_after_release,
    ):
        run_task = asyncio.create_task(
            runner.run(PipelineConfig(library_path=tmp_path), stop_event=stop_event)
        )
        try:
            await listing_started.wait()
            stop_event.set()
        finally:
            release_listing.set()

        with pytest.raises(PipelineStoppedError):
            await run_task

    mock_font_resolver.resolve.assert_not_awaited()
    mock_filesystem.write_file_atomic.assert_not_awaited()


@pytest.mark.anyio
async def test_analyze_episode_stops_before_repair(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, scan = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    stop_event.set()

    with patch("src.core.pipeline_runner.repair_ass") as repair:
        with pytest.raises(PipelineStoppedError):
            await runner._analyze_episode(
                scan,
                "Show",
                PipelineConfig(library_path=tmp_path, dry_run=True),
                datetime.now(timezone.utc),
                stop_event=stop_event,
                font_resolver=mock_font_resolver,
            )

    repair.assert_not_called()
    mock_filesystem.write_file_atomic.assert_not_awaited()


@pytest.mark.anyio
async def test_analyze_episode_stops_after_repair_before_writing_temp_subtitle(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, scan = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    repair_started = asyncio.Event()
    release_repair = threading.Event()
    loop = asyncio.get_running_loop()

    def repair_after_release(_subtitle_path: Path) -> str:
        loop.call_soon_threadsafe(repair_started.set)
        release_repair.wait()
        return "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial"

    with patch(
        "src.core.pipeline_runner.repair_ass",
        side_effect=repair_after_release,
    ):
        analysis_task = asyncio.create_task(
            runner._analyze_episode(
                scan,
                "Show",
                PipelineConfig(library_path=tmp_path),
                datetime.now(timezone.utc),
                stop_event=stop_event,
                font_resolver=mock_font_resolver,
            )
        )
        try:
            await repair_started.wait()
            stop_event.set()
        finally:
            release_repair.set()

        with pytest.raises(PipelineStoppedError):
            await analysis_task

    mock_filesystem.write_file_atomic.assert_not_awaited()
    mock_subprocess.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_analyze_episode_stops_before_sync(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, scan = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()

    async def write_temp_subtitle_then_stop(*_args, **_kwargs) -> None:
        stop_event.set()

    mock_filesystem.write_file_atomic.side_effect = write_temp_subtitle_then_stop

    with pytest.raises(PipelineStoppedError):
        await runner._analyze_episode(
            scan,
            "Show",
            PipelineConfig(library_path=tmp_path, sync_enabled=True),
            datetime.now(timezone.utc),
            stop_event=stop_event,
            font_resolver=mock_font_resolver,
        )

    mock_subprocess.execute.assert_not_awaited()
    mock_font_resolver.resolve.assert_not_awaited()


@pytest.mark.anyio
async def test_analyze_episode_stops_after_sync_before_font_resolution(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, scan = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    sync_started = asyncio.Event()
    release_sync = asyncio.Event()

    async def sync_after_release(*_args, **_kwargs) -> ToolResult:
        sync_started.set()
        await release_sync.wait()
        return ToolResult(
            tool_name="alass",
            success=True,
            exit_code=0,
            stdout="offset 0.0",
            stderr="",
            duration_ms=1.0,
        )

    mock_subprocess.execute.side_effect = sync_after_release
    analysis_task = asyncio.create_task(
        runner._analyze_episode(
            scan,
            "Show",
            PipelineConfig(library_path=tmp_path, dry_run=True, sync_enabled=True),
            datetime.now(timezone.utc),
            stop_event=stop_event,
            font_resolver=mock_font_resolver,
        )
    )
    await sync_started.wait()
    stop_event.set()
    release_sync.set()

    with pytest.raises(PipelineStoppedError):
        await analysis_task

    mock_font_resolver.resolve.assert_not_awaited()


@pytest.mark.anyio
async def test_analyze_episode_stops_after_font_resolution_before_mux_planning(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, scan = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    resolution_started = asyncio.Event()
    release_resolution = asyncio.Event()

    async def resolve_after_release(query):
        resolution_started.set()
        await release_resolution.wait()
        return FontAsset(
            name=query.requested_name,
            file_path=tmp_path / "Arial.ttf",
            source="test",
            layer_found=1,
            cache_hit=False,
            nameids={},
        )

    mock_font_resolver.resolve.side_effect = resolve_after_release
    analysis_task = asyncio.create_task(
        runner._analyze_episode(
            scan,
            "Show",
            PipelineConfig(library_path=tmp_path, dry_run=True),
            datetime.now(timezone.utc),
            stop_event=stop_event,
            font_resolver=mock_font_resolver,
        )
    )
    await resolution_started.wait()
    stop_event.set()
    release_resolution.set()

    with pytest.raises(PipelineStoppedError):
        await analysis_task

    mock_filesystem.write_file_atomic.assert_not_awaited()


@pytest.mark.anyio
async def test_pipeline_runner_stop_during_mux_finishes_owned_binary_without_success_artifacts(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, _ = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    mux_started = asyncio.Event()
    release_mux = asyncio.Event()
    mux_cancelled = asyncio.Event()

    async def mux_after_release(*_args, **_kwargs) -> ToolResult:
        mux_started.set()
        try:
            await release_mux.wait()
        except asyncio.CancelledError:
            mux_cancelled.set()
            raise
        return ToolResult(
            tool_name="mkvmerge",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
        )

    mock_subprocess.execute.side_effect = mux_after_release
    checkpoint_manager = MagicMock()
    checkpoint_manager.load = AsyncMock(return_value=None)
    checkpoint_manager.save = AsyncMock()
    checkpoint_manager.clear = AsyncMock()
    undo_service = MagicMock()
    undo_service.save_manifest = AsyncMock()
    undo_service.create_manifest_id = MagicMock(return_value="run-id")

    run_task = asyncio.create_task(
        runner.run(
            PipelineConfig(library_path=tmp_path),
            stop_event=stop_event,
            checkpoint_manager=checkpoint_manager,
            undo_service=undo_service,
        )
    )
    await mux_started.wait()
    stop_event.set()
    release_mux.set()

    with pytest.raises(PipelineStoppedError):
        await run_task

    assert not mux_cancelled.is_set()
    mock_filesystem.move_to_trash.assert_not_awaited()
    mock_filesystem.replace_file.assert_not_awaited()
    assert all(
        call.args[0].name != "_AnimeStudio_Report.md"
        for call in mock_filesystem.write_file_atomic.await_args_list
    )
    checkpoint_manager.clear.assert_not_awaited()
    undo_service.save_manifest.assert_not_awaited()


@pytest.mark.anyio
async def test_pipeline_runner_native_cancellation_cleans_up_owned_mux_task(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, _ = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    mux_started = asyncio.Event()
    mux_cancelled = asyncio.Event()
    never_complete = asyncio.Event()

    async def block_mux(*_args, **_kwargs) -> ToolResult:
        mux_started.set()
        try:
            await never_complete.wait()
        except asyncio.CancelledError:
            mux_cancelled.set()
            raise
        raise AssertionError("The native cancellation test must cancel mkvmerge.")

    mock_subprocess.execute.side_effect = block_mux
    run_task = asyncio.create_task(runner.run(PipelineConfig(library_path=tmp_path)))
    await mux_started.wait()
    run_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await run_task

    assert mux_cancelled.is_set()
    mock_filesystem.move_to_trash.assert_not_awaited()
    mock_filesystem.replace_file.assert_not_awaited()
    assert all(
        call.args[0].name != "_AnimeStudio_Report.md"
        for call in mock_filesystem.write_file_atomic.await_args_list
    )


@pytest.mark.anyio
async def test_pipeline_runner_stop_after_checkpoint_save_skips_mux_and_completion(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, _ = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    checkpoint_manager = MagicMock()
    checkpoint_manager.load = AsyncMock(return_value=None)

    async def save_checkpoint_then_stop(*_args, **_kwargs) -> None:
        stop_event.set()

    checkpoint_manager.save = AsyncMock(side_effect=save_checkpoint_then_stop)
    checkpoint_manager.clear = AsyncMock()
    undo_service = MagicMock()
    undo_service.save_manifest = AsyncMock()
    undo_service.create_manifest_id = MagicMock(return_value="run-id")

    with pytest.raises(PipelineStoppedError):
        await runner.run(
            PipelineConfig(library_path=tmp_path, dry_run=True),
            stop_event=stop_event,
            checkpoint_manager=checkpoint_manager,
            undo_service=undo_service,
        )

    checkpoint_manager.save.assert_awaited_once()
    checkpoint_manager.clear.assert_not_awaited()
    mock_subprocess.execute.assert_not_awaited()
    mock_filesystem.write_file_atomic.assert_not_awaited()
    undo_service.save_manifest.assert_not_awaited()


@pytest.mark.anyio
async def test_pipeline_runner_stop_after_report_write_skips_manifest_and_checkpoint(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, _ = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()

    async def write_report_then_stop(*_args, **_kwargs) -> None:
        stop_event.set()

    mock_filesystem.write_file_atomic.side_effect = write_report_then_stop
    checkpoint_manager = MagicMock()
    checkpoint_manager.load = AsyncMock(return_value=None)
    checkpoint_manager.save = AsyncMock()
    checkpoint_manager.clear = AsyncMock()
    undo_service = MagicMock()
    undo_service.save_manifest = AsyncMock()
    undo_service.create_manifest_id = MagicMock(return_value="run-id")

    with pytest.raises(PipelineStoppedError):
        await runner.run(
            PipelineConfig(library_path=tmp_path, dry_run=True),
            stop_event=stop_event,
            checkpoint_manager=checkpoint_manager,
            undo_service=undo_service,
        )

    mock_filesystem.write_file_atomic.assert_awaited_once()
    assert (
        mock_filesystem.write_file_atomic.await_args.args[0].name
        == "_AnimeStudio_Report.md"
    )
    undo_service.save_manifest.assert_not_awaited()
    checkpoint_manager.clear.assert_not_awaited()


@pytest.mark.anyio
async def test_pipeline_runner_stop_after_manifest_save_skips_checkpoint_clear(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, _ = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    checkpoint_manager = MagicMock()
    checkpoint_manager.load = AsyncMock(return_value=None)
    checkpoint_manager.save = AsyncMock()
    checkpoint_manager.clear = AsyncMock()
    undo_service = MagicMock()

    async def save_manifest_then_stop(*_args, **_kwargs) -> None:
        stop_event.set()

    undo_service.save_manifest = AsyncMock(side_effect=save_manifest_then_stop)
    undo_service.create_manifest_id = MagicMock(return_value="run-id")

    with pytest.raises(PipelineStoppedError):
        await runner.run(
            PipelineConfig(library_path=tmp_path, dry_run=True),
            stop_event=stop_event,
            checkpoint_manager=checkpoint_manager,
            undo_service=undo_service,
        )

    mock_filesystem.write_file_atomic.assert_awaited_once()
    undo_service.save_manifest.assert_awaited_once()
    checkpoint_manager.clear.assert_not_awaited()


@pytest.mark.anyio
async def test_pipeline_runner_stop_after_checkpoint_clear_never_returns_success(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    scan_output, _ = _single_episode_output(tmp_path)
    runner = _make_runner(
        scan_output,
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()
    checkpoint_manager = MagicMock()
    checkpoint_manager.load = AsyncMock(return_value=None)
    checkpoint_manager.save = AsyncMock()

    async def clear_checkpoint_then_stop(*_args, **_kwargs) -> None:
        stop_event.set()

    checkpoint_manager.clear = AsyncMock(side_effect=clear_checkpoint_then_stop)
    undo_service = MagicMock()
    undo_service.save_manifest = AsyncMock()
    undo_service.create_manifest_id = MagicMock(return_value="run-id")

    with pytest.raises(PipelineStoppedError):
        await runner.run(
            PipelineConfig(library_path=tmp_path, dry_run=True),
            stop_event=stop_event,
            checkpoint_manager=checkpoint_manager,
            undo_service=undo_service,
        )

    mock_filesystem.write_file_atomic.assert_awaited_once()
    undo_service.save_manifest.assert_awaited_once()
    checkpoint_manager.clear.assert_awaited_once()


@pytest.mark.anyio
async def test_pipeline_runner_stop_after_empty_report_write_never_returns_report(
    tmp_path,
    mock_font_resolver,
    mock_subprocess,
    mock_filesystem,
    mock_tool_registry,
    mock_font_ingestion_service,
    disk_semaphore,
    app_config,
):
    runner = _make_runner(
        LibraryScanOutput(episodes=[], font_directories=[]),
        mock_font_resolver,
        mock_subprocess,
        mock_filesystem,
        mock_tool_registry,
        mock_font_ingestion_service,
        disk_semaphore,
        app_config,
    )
    stop_event = asyncio.Event()

    async def write_empty_report_then_stop(*_args, **_kwargs) -> None:
        stop_event.set()

    mock_filesystem.write_file_atomic.side_effect = write_empty_report_then_stop

    with pytest.raises(PipelineStoppedError):
        await runner.run(PipelineConfig(library_path=tmp_path), stop_event=stop_event)

    mock_filesystem.write_file_atomic.assert_awaited_once()
    assert (
        mock_filesystem.write_file_atomic.await_args.args[0].name
        == "_AnimeStudio_Report.md"
    )
