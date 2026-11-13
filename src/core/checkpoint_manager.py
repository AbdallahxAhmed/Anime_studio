import asyncio
import json
import tomllib
from pathlib import Path
from src.models.run_manifest import PipelineCheckpoint


class CheckpointManager:
    """Manages the pipeline checkpoint persistence using TOML."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.checkpoint_path = self.data_dir / "pipeline_checkpoint.toml"

    async def save(self, checkpoint: PipelineCheckpoint) -> None:
        """Save the checkpoint atomically in a separate thread."""
        await asyncio.to_thread(self._save_sync, checkpoint)

    def _save_sync(self, checkpoint: PipelineCheckpoint) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # JSON strings are valid TOML basic strings and escape Windows
        # backslashes and quotes correctly (raw f-strings did not).
        quote = json.dumps
        lines = [
            f"library_path = {quote(str(checkpoint.library_path))}",
            f"timestamp = {quote(checkpoint.timestamp)}",
            "",
            "completed_episodes = [",
        ]
        for ep in checkpoint.completed_episodes:
            lines.append(f"  {quote(str(ep))},")
        lines.append("]")
        lines.append("")
        lines.append("selected_paths = [")
        for sp in checkpoint.selected_paths:
            lines.append(f"  {quote(str(sp))},")
        lines.append("]")

        # Write to a temp file first, then replace atomically
        temp_path = self.checkpoint_path.with_suffix(".tmp")
        temp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temp_path.replace(self.checkpoint_path)

    async def load(self) -> PipelineCheckpoint | None:
        """Load the checkpoint in a separate thread."""
        return await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> PipelineCheckpoint | None:
        if not self.checkpoint_path.is_file():
            return None
        try:
            with self.checkpoint_path.open("rb") as f:
                data = tomllib.load(f)
            return PipelineCheckpoint(
                library_path=data["library_path"],
                completed_episodes=tuple(data.get("completed_episodes", [])),
                timestamp=data["timestamp"],
                selected_paths=tuple(data.get("selected_paths", [])),
            )
        except Exception:
            return None

    async def clear(self) -> None:
        """Clear the checkpoint file."""
        await asyncio.to_thread(self._clear_sync)

    def _clear_sync(self) -> None:
        if self.checkpoint_path.is_file():
            try:
                self.checkpoint_path.unlink()
            except OSError:
                pass

    def exists_for_library(self, library_path: Path) -> bool:
        """Check if a checkpoint exists for the specified library."""
        return self._exists_for_library_sync(library_path)

    def _exists_for_library_sync(self, library_path: Path) -> bool:
        checkpoint = self._load_sync()
        if checkpoint is None:
            return False
        try:
            return (
                Path(checkpoint.library_path).resolve() == Path(library_path).resolve()
            )
        except Exception:
            return False
