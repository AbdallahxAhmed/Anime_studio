import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.adapters.mkvextract import MkvextractAdapter
from src.models.tool_result import ToolResult
from src.ports.subprocess import SubprocessPort


@pytest.fixture
def mock_subprocess():
    sub = MagicMock(spec=SubprocessPort)
    sub.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="mkvextract",
            success=True,
            exit_code=0,
            stdout="Extracting track 0 with the CodecID 'S_TEXT/ASS' to the file...\n",
            stderr="",
            duration_ms=50.0,
        )
    )
    return sub


@pytest.mark.asyncio
async def test_mkvextract_extract_track_success(mock_subprocess):
    adapter = MkvextractAdapter(mock_subprocess)
    mkv_path = Path("/anime/ep1.mkv")
    output_path = Path("/trash/ep1.tmp.ass")

    result = await adapter.extract_track(mkv_path, track_id=2, output_path=output_path)

    assert result.success is True
    call_args = mock_subprocess.execute.call_args[0][0]
    assert call_args == [
        "mkvextract",
        "tracks",
        str(mkv_path),
        f"2:{output_path}",
    ]


@pytest.mark.asyncio
async def test_mkvextract_extract_track_failure(mock_subprocess):
    mock_subprocess.execute.return_value = ToolResult(
        tool_name="mkvextract",
        success=False,
        exit_code=2,
        stdout="",
        stderr="Error: track ID 99 does not exist",
        duration_ms=30.0,
    )
    adapter = MkvextractAdapter(mock_subprocess)
    result = await adapter.extract_track(
        Path("/anime/ep1.mkv"), track_id=99, output_path=Path("/trash/out.ass")
    )

    assert result.success is False
    assert result.exit_code == 2
