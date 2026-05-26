from pathlib import Path
import structlog
from src.models.tool_result import ToolResult
from src.ports.subprocess import SubprocessPort

logger = structlog.get_logger()


class FfsubsyncAdapter:
    def __init__(self, subprocess_port: SubprocessPort) -> None:
        self.subprocess_port = subprocess_port

    async def sync(
        self,
        reference_mkv: Path,
        subtitle_ass: Path,
        output_ass: Path,
        timeout: float = 120.0,
    ) -> ToolResult:
        """Sync subtitle_ass to reference_mkv audio using ffsubsync, writing to output_ass."""
        args = [
            "ffsubsync",
            str(reference_mkv),
            "-i",
            str(subtitle_ass),
            "-o",
            str(output_ass),
        ]
        logger.info("executing ffsubsync sync", args=args)
        return await self.subprocess_port.execute(args, timeout=timeout)
