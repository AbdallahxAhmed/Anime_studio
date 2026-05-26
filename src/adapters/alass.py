from pathlib import Path
import structlog
from src.models.tool_result import ToolResult
from src.ports.subprocess import SubprocessPort

logger = structlog.get_logger()


class AlassAdapter:
    def __init__(self, subprocess_port: SubprocessPort) -> None:
        self.subprocess_port = subprocess_port

    async def sync(
        self,
        reference_mkv: Path,
        subtitle_ass: Path,
        output_ass: Path,
        timeout: float = 120.0,
    ) -> ToolResult:
        """Sync subtitle_ass to reference_mkv audio using alass, writing to output_ass."""
        args = ["alass", str(reference_mkv), str(subtitle_ass), str(output_ass)]
        logger.info("executing alass sync", args=args)
        return await self.subprocess_port.execute(args, timeout=timeout)
