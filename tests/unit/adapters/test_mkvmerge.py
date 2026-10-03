import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.adapters.mkvmerge import MkvmergeAdapter
from src.errors import ToolExecutionError
from src.models.font import FontAsset
from src.models.mux import MuxJob
from src.models.tool_result import ToolResult
from src.ports.subprocess import SubprocessPort


@pytest.fixture
def mock_subprocess():
    sub = MagicMock(spec=SubprocessPort)
    sub.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="mkvmerge",
            success=True,
            exit_code=0,
            stdout="Muxing took 1 second.\n",
            stderr="",
            duration_ms=100.0,
        )
    )
    return sub


@pytest.mark.asyncio
async def test_mkvmerge_mux_standard(mock_subprocess):
    adapter = MkvmergeAdapter(mock_subprocess)
    font = FontAsset(
        name="Arial",
        file_path=Path("/fonts/arial.ttf"),
        source="system",
        layer_found=1,
        cache_hit=True,
        nameids={1: "Arial"},
    )
    job = MuxJob(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/anime/ep1.ass"),
        fonts=[font],
        output_path=Path("/output/ep1.mkv"),
        replace_embedded_subtitles=False,
    )

    result = await adapter.mux(job)

    assert result.success is True
    assert result.fonts_attached == 1
    call_args = mock_subprocess.execute.call_args[0][0]
    assert call_args == [
        "mkvmerge",
        "-o",
        str(Path("/output/ep1.mkv")),
        str(Path("/anime/ep1.mkv")),
        str(Path("/anime/ep1.ass")),
        "--attach-file",
        str(Path("/fonts/arial.ttf")),
    ]


@pytest.mark.asyncio
async def test_mkvmerge_mux_replace_embedded(mock_subprocess):
    adapter = MkvmergeAdapter(mock_subprocess)
    job = MuxJob(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/trash/extracted.tmp.ass"),
        fonts=[],
        output_path=Path("/output/ep1.mkv"),
        replace_embedded_subtitles=True,
    )

    result = await adapter.mux(job)

    assert result.success is True
    assert result.fonts_attached == 0
    call_args = mock_subprocess.execute.call_args[0][0]
    assert call_args == [
        "mkvmerge",
        "-o",
        str(Path("/output/ep1.mkv")),
        "--no-subtitles",
        str(Path("/anime/ep1.mkv")),
        str(Path("/trash/extracted.tmp.ass")),
    ]


@pytest.mark.asyncio
async def test_mkvmerge_mux_warnings(mock_subprocess):
    mock_subprocess.execute.return_value = ToolResult(
        tool_name="mkvmerge",
        success=True,
        exit_code=1,
        stdout="Warning: track 0 has unknown language\n",
        stderr="Warning: font attachment name collision\n",
        duration_ms=150.0,
    )
    adapter = MkvmergeAdapter(mock_subprocess)
    job = MuxJob(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/anime/ep1.ass"),
        fonts=[],
        output_path=Path("/output/ep1.mkv"),
    )

    result = await adapter.mux(job)

    assert result.success is True
    assert len(result.warnings) == 2
    assert "unknown language" in result.warnings[0]


@pytest.mark.asyncio
async def test_mkvmerge_mux_failure(mock_subprocess):
    mock_subprocess.execute.return_value = ToolResult(
        tool_name="mkvmerge",
        success=False,
        exit_code=2,
        stdout="",
        stderr="Error: broken container\n",
        duration_ms=50.0,
    )
    adapter = MkvmergeAdapter(mock_subprocess)
    job = MuxJob(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/anime/ep1.ass"),
        fonts=[],
        output_path=Path("/output/ep1.mkv"),
    )

    result = await adapter.mux(job)

    assert result.success is False


@pytest.mark.asyncio
async def test_mkvmerge_identify_success(mock_subprocess):
    mock_subprocess.execute.return_value = ToolResult(
        tool_name="mkvmerge",
        success=True,
        exit_code=0,
        stdout='{"tracks": [{"id": 0, "type": "video"}]}',
        stderr="",
        duration_ms=20.0,
    )
    adapter = MkvmergeAdapter(mock_subprocess)
    data = await adapter.identify(Path("/anime/ep1.mkv"))

    assert "tracks" in data
    assert len(data["tracks"]) == 1


@pytest.mark.asyncio
async def test_mkvmerge_identify_failure(mock_subprocess):
    mock_subprocess.execute.return_value = ToolResult(
        tool_name="mkvmerge",
        success=False,
        exit_code=2,
        stdout="",
        stderr="Cannot open file",
        duration_ms=20.0,
    )
    adapter = MkvmergeAdapter(mock_subprocess)

    with pytest.raises(ToolExecutionError, match="Failed to identify"):
        await adapter.identify(Path("/anime/ep1.mkv"))
