import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.adapters.alass import AlassAdapter
from src.ports.subprocess import SubprocessPort
from src.models.tool_result import ToolResult


@pytest.mark.anyio
async def test_alass_sync():
    sub = MagicMock(spec=SubprocessPort)
    expected_result = ToolResult(
        tool_name="alass",
        success=True,
        exit_code=0,
        stdout="sync offset: 1.2s",
        stderr="",
        duration_ms=100.0,
    )
    sub.execute = AsyncMock(return_value=expected_result)

    adapter = AlassAdapter(sub)
    res = await adapter.sync(
        reference_mkv=Path("ref.mkv"),
        subtitle_ass=Path("sub.ass"),
        output_ass=Path("out.ass"),
        timeout=60.0,
    )

    assert res == expected_result
    sub.execute.assert_called_once_with(
        ["alass", "ref.mkv", "sub.ass", "out.ass"],
        timeout=60.0,
    )
