import pytest
from pydantic import ValidationError

from src.models.tool_result import ToolResult


def test_tool_result_valid():
    res = ToolResult(
        tool_name="mkvmerge",
        success=True,
        exit_code=0,
        stdout="All fonts attached.",
        duration_ms=450.5,
    )
    assert res.tool_name == "mkvmerge"
    assert res.success is True
    assert res.stderr == ""
    assert res.suggestion is None

    # Test JSON round-trip
    dumped = res.model_dump(mode="json")
    assert dumped["tool_name"] == "mkvmerge"
    assert dumped["success"] is True
    assert dumped["exit_code"] == 0
    assert dumped["stdout"] == "All fonts attached."
    assert dumped["stderr"] == ""
    assert dumped["duration_ms"] == 450.5
    assert dumped["suggestion"] is None


def test_tool_result_failure_with_suggestion():
    res = ToolResult(
        tool_name="alass",
        success=False,
        exit_code=1,
        stderr="Error: Timing mismatch.",
        duration_ms=1200.0,
        suggestion="Try using ffsubsync as fallback.",
    )
    assert res.success is False
    assert res.exit_code == 1
    assert res.suggestion == "Try using ffsubsync as fallback."


def test_tool_result_immutability():
    res = ToolResult(
        tool_name="ffmpeg",
        success=True,
        exit_code=0,
        duration_ms=10.0,
    )
    with pytest.raises(ValidationError):
        res.success = False


def test_tool_result_validation():
    with pytest.raises(ValidationError):
        # negative duration_ms
        ToolResult(
            tool_name="ffmpeg",
            success=True,
            exit_code=0,
            duration_ms=-5.0,
        )
