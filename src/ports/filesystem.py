from pathlib import Path
from typing import Protocol, runtime_checkable
from src.models.trash import TrashReceipt


@runtime_checkable
class FilesystemPort(Protocol):
    async def move_to_trash(
        self,
        source: Path,
        trash_receipt: TrashReceipt,
    ) -> None:
        """Move source file to trash directory per receipt. Create trash dir if needed."""
        ...

    async def write_file_atomic(
        self,
        target: Path,
        content: str,
        encoding: str = "utf-8",
    ) -> None:
        """Write content to target via temp file + atomic rename."""
        ...

    async def ensure_directory(self, path: Path) -> None:
        """Create directory and parents if needed."""
        ...

    async def replace_file(self, source: Path, target: Path) -> None:
        """Atomically replace target with source."""
        ...
