import asyncio
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.pipeline_runner import PipelineRunner
from src.core.font_resolver import FontResolver
from src.core.library_scanner import LibraryScanner
from src.ports.subprocess import SubprocessPort
from src.ports.filesystem import FilesystemPort
from src.adapters.dependency_checker import ToolRegistry
from src.config import AppConfig
from src.models.pipeline import LibraryScanResult, PipelineConfig, LibraryScanOutput
from src.models.report import EpisodeStatus
from src.models.font import FontAsset
from src.models.tool_result import ToolResult
from src.core.font_ingestion import FontIngestionService


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
            selected_paths=frozenset({Path("/anime/Show A")}),
        )
        report = await runner.run(cfg)

        # Show A is processed. Show B is not in report because /anime is a mock path and has no files on disk.
        processed = [e for e in report.episodes if e.status != EpisodeStatus.SKIPPED]
        assert len(processed) == 1
        assert processed[0].episode_path == Path("/anime/Show A/episode_01.mkv")


@pytest.mark.anyio
async def test_pipeline_runner_stop_event_stops_processing(
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

    repaired_content = "dummy"
    with patch(
        "src.core.pipeline_runner.repair_ass", MagicMock(return_value=repaired_content)
    ):
        cfg = PipelineConfig(library_path=Path("/anime"))
        report = await runner.run(cfg, stop_event=stop_event)

        # Should stop before analyzing any episodes
        assert (
            len(report.episodes) == 2
        )  # Total episodes scanned, but they are all skipped/not complete
        completed = [e for e in report.episodes if e.status == EpisodeStatus.COMPLETE]
        assert len(completed) == 0


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
