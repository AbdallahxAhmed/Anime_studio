import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.pipeline_runner import PipelineRunner
from src.core.font_resolver import FontResolver
from src.ports.subprocess import SubprocessPort
from src.ports.filesystem import FilesystemPort
from src.adapters.dependency_checker import ToolRegistry
from src.config import AppConfig
from src.models.pipeline import LibraryScanResult, PipelineConfig
from src.models.report import EpisodeStatus
from src.models.font import FontAsset
from src.models.tool_result import ToolResult


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
def app_config():
    return AppConfig(max_concurrent_disk_io=2)


@pytest.mark.anyio
async def test_pipeline_runner_empty_library(
    mock_font_resolver, mock_subprocess, mock_filesystem, mock_tool_registry, app_config
):
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
    )

    # Point to an empty directory mock
    with patch("src.core.pipeline_runner.scan_library", AsyncMock(return_value=[])):
        cfg = PipelineConfig(library_path=Path("/empty"))
        report = await runner.run(cfg)

        assert report.total_fonts_found == 0
        assert len(report.episodes) == 0
        mock_filesystem.write_file_atomic.assert_called_once()


@pytest.mark.anyio
async def test_pipeline_runner_success(
    mock_font_resolver, mock_subprocess, mock_filesystem, mock_tool_registry, app_config
):
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
    )

    scan_res = [
        LibraryScanResult(
            episode_path=Path("/anime/cool_show_01.mkv"),
            subtitle_path=Path("/anime/cool_show_01.ass"),
            anime_title="Cool Show",
        )
    ]

    repaired_content = "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial"

    with (
        patch(
            "src.core.pipeline_runner.scan_library", AsyncMock(return_value=scan_res)
        ),
        patch(
            "src.core.pipeline_runner.repair_ass",
            MagicMock(return_value=repaired_content),
        ),
    ):
        cfg = PipelineConfig(library_path=Path("/anime"), dry_run=False)
        report = await runner.run(cfg)

        assert len(report.episodes) == 1
        assert report.episodes[0].status == EpisodeStatus.COMPLETE
        assert report.total_fonts_found == 1
        mock_filesystem.move_to_trash.assert_called()
        mock_filesystem.replace_file.assert_called_once()


@pytest.mark.anyio
async def test_pipeline_runner_subtitle_sync_fallback(
    mock_font_resolver, mock_subprocess, mock_filesystem, mock_tool_registry, app_config
):
    # Setup runner
    runner = PipelineRunner(
        font_resolver=mock_font_resolver,
        subprocess_adapter=mock_subprocess,
        filesystem=mock_filesystem,
        tool_registry=mock_tool_registry,
        config=app_config,
    )

    scan_res = [
        LibraryScanResult(
            episode_path=Path("/anime/ep1.mkv"),
            subtitle_path=Path("/anime/ep1.ass"),
            anime_title="Show",
        )
    ]
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
            "src.core.pipeline_runner.scan_library", AsyncMock(return_value=scan_res)
        ),
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
