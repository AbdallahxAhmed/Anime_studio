from typing import Protocol, runtime_checkable
from pathlib import Path


@runtime_checkable
class MkvmergePort(Protocol):
    async def identify(self, file_path: Path, timeout: float = 30.0) -> dict:
        """Run mkvmerge -J on a file and return the parsed identification dict.

        Args:
            file_path: Path to the MKV file to identify.
            timeout: Optional timeout in seconds.

        Returns:
            Parsed JSON dict from mkvmerge identification output.

        Raises:
            ToolExecutionError: If mkvmerge fails to identify the file.
        """
        ...
