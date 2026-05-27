import asyncio
import time
from typing import Sequence, Any
import structlog

from src.models.tool_result import ToolResult
from src.ports.subprocess import SubprocessPort
from pathlib import Path

logger = structlog.get_logger()


class SubprocessAdapter(SubprocessPort):
    def __init__(self, tool_registry: Any = None) -> None:
        self.tool_registry = tool_registry

    async def execute(
        self,
        args: Sequence[str],
        timeout: float | None = None,
    ) -> ToolResult:
        if not args:
            return ToolResult(
                tool_name="",
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_ms=0.0,
                suggestion="empty command arguments",
            )

        tool_name = args[0]
        # Resolve to absolute path using tool_registry if available
        if self.tool_registry and not Path(tool_name).is_absolute():
            resolved = self.tool_registry.get(tool_name)
            if resolved and resolved.is_available:
                tool_name = str(resolved.path)

        start_time = time.perf_counter()
        process = None

        try:
            # Strictly use asyncio.create_subprocess_exec
            process = await asyncio.create_subprocess_exec(
                tool_name,
                *args[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Use asyncio.wait_for(process.communicate(), timeout) for timeout enforcement
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    exit_code=-2,
                    stdout="",
                    stderr="",
                    duration_ms=duration_ms,
                    suggestion="timed out",
                )

            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Decode with errors="replace"
            stdout_str = stdout_bytes.decode(errors="replace")
            stderr_str = stderr_bytes.decode(errors="replace")

            success = process.returncode == 0

            logger.info(
                "subprocess executed",
                tool_name=tool_name,
                duration_ms=duration_ms,
                exit_code=process.returncode,
                success=success,
            )

            return ToolResult(
                tool_name=tool_name,
                success=success,
                exit_code=process.returncode,
                stdout=stdout_str,
                stderr=stderr_str,
                duration_ms=duration_ms,
            )

        except FileNotFoundError as e:
            logger.error(f"subprocess tool not found: {tool_name} (error: {e})")
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult(
                tool_name=tool_name,
                success=False,
                exit_code=-3,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                suggestion=f"tool not found: {e}",
            )
        except Exception as e:
            logger.error(
                f"subprocess execution exception occurred: {tool_name} (error: {e})"
            )
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            if process:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
            return ToolResult(
                tool_name=tool_name,
                success=False,
                exit_code=-4,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                suggestion=f"execution error: {e}",
            )
