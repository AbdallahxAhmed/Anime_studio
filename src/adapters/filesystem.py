import asyncio
import shutil
from pathlib import Path
import structlog
from src.models.trash import TrashReceipt
from src.ports.filesystem import FilesystemPort

logger = structlog.get_logger()


class FilesystemAdapter(FilesystemPort):
    async def move_to_trash(
        self,
        source: Path,
        trash_receipt: TrashReceipt,
    ) -> None:
        """Move source file to trash directory per receipt. Create trash dir if needed."""

        def _move():
            src_path = Path(source)
            dest_path = Path(trash_receipt.trash_path)

            if not src_path.exists():
                logger.warning("source file for trash does not exist", source=src_path)
                return

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dest_path))
            logger.info("moved file to trash", source=src_path, trash=dest_path)

        await asyncio.to_thread(_move)

    async def write_file_atomic(
        self,
        target: Path,
        content: str,
        encoding: str = "utf-8",
    ) -> None:
        """Write content to target via temp file + atomic rename."""

        def _write():
            target_path = Path(target)
            target_path.parent.mkdir(parents=True, exist_ok=True)

            temp_path = target_path.with_name(f"{target_path.name}.tmp")
            try:
                with open(temp_path, "w", encoding=encoding) as f:
                    f.write(content)
                temp_path.replace(target_path)
                logger.debug("atomically wrote file", target=target_path)
            except Exception as e:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                logger.error(
                    "failed to write file atomically", target=target_path, error=str(e)
                )
                raise e

        await asyncio.to_thread(_write)

    async def ensure_directory(self, path: Path) -> None:
        """Create directory and parents if needed."""

        def _mkdir():
            Path(path).mkdir(parents=True, exist_ok=True)
            logger.debug("ensured directory exists", path=path)

        await asyncio.to_thread(_mkdir)

    async def replace_file(self, source: Path, target: Path) -> None:
        """Atomically replace target with source."""

        def _replace():
            src_path = Path(source)
            dest_path = Path(target)
            if dest_path.exists():
                dest_path.unlink()
            shutil.move(str(src_path), str(dest_path))
            logger.info("replaced file", source=src_path, target=dest_path)

        await asyncio.to_thread(_replace)
