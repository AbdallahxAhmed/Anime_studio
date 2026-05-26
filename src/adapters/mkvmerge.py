import json
from pathlib import Path
import structlog
from src.models.mux import MuxJob, MuxResult
from src.ports.subprocess import SubprocessPort
from src.errors import ToolExecutionError

logger = structlog.get_logger()


class MkvmergeAdapter:
    def __init__(self, subprocess_port: SubprocessPort) -> None:
        self.subprocess_port = subprocess_port

    async def mux(self, job: MuxJob, timeout: float = 300.0) -> MuxResult:
        """Mux the episode, subtitle, and fonts together into a new MKV."""
        args = [
            "mkvmerge",
            "-o",
            str(job.output_path),
            str(job.episode_path),
            str(job.subtitle_path),
        ]
        for font in job.fonts:
            args.extend(["--attach-file", str(font.file_path)])

        logger.info("executing mkvmerge mux", args=args, output=job.output_path)
        tool_result = await self.subprocess_port.execute(args, timeout=timeout)

        # mkvmerge returns 0 for success/no warnings, 1 for success with warnings, 2 for error
        success = tool_result.exit_code in (0, 1)

        warnings = []
        # Extract warning lines from both stdout and stderr
        for output_str in (tool_result.stdout, tool_result.stderr):
            if output_str:
                for line in output_str.splitlines():
                    if "warning" in line.lower() or line.strip().startswith("Warning:"):
                        warnings.append(line.strip())

        if not success:
            logger.error(
                "mkvmerge mux failed",
                exit_code=tool_result.exit_code,
                stderr=tool_result.stderr,
            )

        return MuxResult(
            success=success,
            output_path=job.output_path,
            duration_ms=tool_result.duration_ms,
            fonts_attached=len(job.fonts),
            warnings=warnings,
        )

    async def identify(self, file_path: Path, timeout: float = 30.0) -> dict:
        """Run mkvmerge -J on a file and return the parsed identification dict."""
        args = ["mkvmerge", "-J", str(file_path)]
        tool_result = await self.subprocess_port.execute(args, timeout=timeout)

        if not tool_result.success:
            raise ToolExecutionError(
                f"Failed to identify file {file_path}: {tool_result.stderr or tool_result.stdout}"
            )

        try:
            return json.loads(tool_result.stdout)
        except Exception as e:
            raise ToolExecutionError(f"Failed to parse mkvmerge -J JSON output: {e}")
