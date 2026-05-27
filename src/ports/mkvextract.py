from typing import Protocol, runtime_checkable
from pathlib import Path
from src.models.tool_result import ToolResult


@runtime_checkable
class MkvextractPort(Protocol):
    async def extract_track(
        self,
        mkv_path: Path,
        track_id: int,
        output_path: Path,
        timeout: float = 120.0,
    ) -> ToolResult:
        """Extract a single track from an MKV file via mkvextract.

        Args:
            mkv_path: Path to the source MKV file.
            track_id: 0-based track ID (from mkvmerge -J "id" field).
            output_path: Path to write the extracted track to.
            timeout: Timeout in seconds.

        Returns:
            ToolResult describing the extraction outcome.
        """
        ...
