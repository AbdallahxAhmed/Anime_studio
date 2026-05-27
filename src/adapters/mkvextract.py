from pathlib import Path
import structlog
from src.ports.subprocess import SubprocessPort
from src.models.tool_result import ToolResult

logger = structlog.get_logger()


class MkvextractAdapter:
    def __init__(self, subprocess_port: SubprocessPort) -> None:
        self.subprocess_port = subprocess_port

    async def extract_track(
        self,
        mkv_path: Path,
        track_id: int,
        output_path: Path,
        timeout: float = 120.0,
    ) -> ToolResult:
        """Extract a single track from an MKV container."""
        args = [
            "mkvextract",
            "tracks",
            str(mkv_path),
            f"{track_id}:{output_path}",
        ]

        logger.info(
            "extracting embedded subtitle track",
            mkv=mkv_path.name,
            track_id=track_id,
            output=str(output_path),
        )

        result = await self.subprocess_port.execute(args, timeout=timeout)

        if result.success:
            logger.info(
                "subtitle track extracted successfully",
                mkv=mkv_path.name,
                track_id=track_id,
                duration_ms=result.duration_ms,
            )
        else:
            logger.error(
                "mkvextract failed",
                mkv=mkv_path.name,
                track_id=track_id,
                exit_code=result.exit_code,
                stderr=result.stderr,
            )

        return result
