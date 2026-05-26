from typing import Protocol, Sequence, runtime_checkable
from src.models.tool_result import ToolResult


@runtime_checkable
class SubprocessPort(Protocol):
    async def execute(
        self,
        args: Sequence[str],
        timeout: float | None = None,
    ) -> ToolResult:
        """Execute an external process asynchronously and return a ToolResult.

        Args:
            args: The command and its arguments.
            timeout: Optional timeout in seconds.

        Returns:
            A ToolResult describing the execution outcome.
        """
        ...
