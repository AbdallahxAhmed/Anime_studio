import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.adapters.ffsubsync import FfsubsyncAdapter
from src.ports.subprocess import SubprocessPort
from src.models.tool_result import ToolResult


@pytest.mark.anyio
async def test_ffsubsync_sync():
    sub = MagicMock(spec=SubprocessPort)
    expected_result = ToolResult(
        tool_name="ffsubsync",
        success=True,
        exit_code=0,
        stdout="ffsubsync offset: 1.2s",
        stderr="",
        duration_ms=100.0,
    )
    sub.execute = AsyncMock(return_value=expected_result)

    adapter = FfsubsyncAdapter(sub)
    res = await adapter.sync(
        reference_mkv=Path("ref.mkv"),
        subtitle_ass=Path("sub.ass"),
        output_ass=Path("out.ass"),
        timeout=60.0,
    )

    assert res == expected_result
    sub.execute.assert_called_once_with(
        ["ffsubsync", "ref.mkv", "-i", "sub.ass", "-o", "out.ass"],
        timeout=60.0,
    )
