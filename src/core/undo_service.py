import asyncio
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List
import structlog

from src.models.run_manifest import RunManifest, EpisodeProcessed
from src.ports.filesystem import FilesystemPort

logger = structlog.get_logger()


@dataclass
class UndoResult:
    restored: int = 0
    failed: int = 0
    missing: int = 0  # trash files already purged
    conflicts: int = 0  # target file already exists


class UndoService:
    """Handles restoring files from trash and managing run manifests."""

    def __init__(
        self, data_dir: Path, filesystem_port: FilesystemPort, max_run_history: int = 10
    ):
        self.data_dir = Path(data_dir)
        self.fs = filesystem_port
        self.max_history = max_run_history
        self.history_dir = self.data_dir / "run_history"

    async def list_runs(self) -> List[RunManifest]:
        """Read all .toml files from data_dir/run_history/ sorted by timestamp descending, capped at max_history."""
        return await asyncio.to_thread(self._list_runs_sync)

    def _list_runs_sync(self) -> List[RunManifest]:
        if not self.history_dir.exists():
            return []
        manifests = []
        for file in self.history_dir.glob("*.toml"):
            try:
                with file.open("rb") as f:
                    data = tomllib.load(f)

                episodes = tuple(
                    EpisodeProcessed(
                        episode_path=ep["episode_path"],
                        trash_receipt_path=ep.get("trash_receipt_path"),
                        show_name=ep.get("show_name", ""),
                        status=ep.get("status", "success"),
                    )
                    for ep in data.get("episodes_processed", [])
                )

                manifests.append(
                    RunManifest(
                        run_id=data["run_id"],
                        timestamp=data["timestamp"],
                        library_path=data["library_path"],
                        episodes_processed=episodes,
                    )
                )
            except Exception as e:
                logger.warning(
                    "Failed to load run manifest", file=file.name, error=str(e)
                )

        # Sort by timestamp descending
        manifests.sort(key=lambda m: m.timestamp, reverse=True)
        return manifests[: self.max_history]

    async def save_manifest(self, manifest: RunManifest) -> None:
        """Write manifest to data_dir/run_history/run_{timestamp}.toml and prune old ones."""
        await asyncio.to_thread(self._save_manifest_sync, manifest)

    def _save_manifest_sync(self, manifest: RunManifest) -> None:
        self.history_dir.mkdir(parents=True, exist_ok=True)

        # Clean timestamp for filename
        ts_clean = manifest.timestamp.replace(":", "-").replace(" ", "_")
        filename = f"run_{ts_clean}.toml"
        filepath = self.history_dir / filename

        # Manual TOML serialization
        lines = [
            f'run_id = "{manifest.run_id}"',
            f'timestamp = "{manifest.timestamp}"',
            f'library_path = "{manifest.library_path}"',
            "",
        ]

        for ep in manifest.episodes_processed:
            lines.append("[[episodes_processed]]")
            lines.append(f'episode_path = "{ep.episode_path}"')
            if ep.trash_receipt_path:
                lines.append(f'trash_receipt_path = "{ep.trash_receipt_path}"')
            lines.append(f'show_name = "{ep.show_name}"')
            lines.append(f'status = "{ep.status}"')
            lines.append("")

        filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Prune older manifests
        all_files = sorted(
            self.history_dir.glob("*.toml"), key=lambda f: f.stat().st_mtime
        )
        if len(all_files) > self.max_history:
            to_delete = all_files[: len(all_files) - self.max_history]
            for f in to_delete:
                try:
                    f.unlink()
                except OSError:
                    pass

    async def undo_episode(
        self, manifest: RunManifest, episode_path: str | Path
    ) -> UndoResult:
        """Undo a single episode by moving it back from trash."""
        # Find episode in manifest
        target_ep = None
        target_idx = -1
        for idx, ep in enumerate(manifest.episodes_processed):
            p1 = Path(ep.episode_path)
            p2 = Path(episode_path)
            matched = False
            if p1 == p2:
                matched = True
            else:
                try:
                    if (
                        p1.resolve().as_posix().lower()
                        == p2.resolve().as_posix().lower()
                    ):
                        matched = True
                except Exception:
                    pass
            if not matched:
                s1 = str(p1).replace("\\", "/").lower()
                s2 = str(p2).replace("\\", "/").lower()
                if s1 == s2:
                    matched = True
            if matched:
                target_ep = ep
                target_idx = idx
                break

        if target_ep is None:
            return UndoResult(failed=1)

        if not target_ep.trash_receipt_path:
            return UndoResult(missing=1)

        trash_path = Path(target_ep.trash_receipt_path)
        original_path = Path(target_ep.episode_path)

        # Check trash file exists
        trash_exists = await asyncio.to_thread(trash_path.is_file)
        if not trash_exists:
            return UndoResult(missing=1)

        # Check destination exists
        dest_exists = await asyncio.to_thread(original_path.is_file)
        if dest_exists:
            return UndoResult(conflicts=1)

        try:
            # MOVE (replace_file)
            await self.fs.replace_file(trash_path, original_path)

            # Update manifest on disk (clear trash receipt path since it's restored)
            new_episodes = list(manifest.episodes_processed)
            new_episodes[target_idx] = replace(target_ep, trash_receipt_path=None)
            new_manifest = replace(manifest, episodes_processed=tuple(new_episodes))
            await self.save_manifest(new_manifest)

            return UndoResult(restored=1)
        except Exception as e:
            logger.error("Undo restore failed", error=str(e), path=episode_path)
            return UndoResult(failed=1)

    async def undo_show(self, manifest: RunManifest, show_name: str) -> UndoResult:
        """Undo all episodes with matching show_name."""
        res = UndoResult()
        for ep in manifest.episodes_processed:
            if ep.show_name == show_name:
                # Call undo_episode which updates the manifest incrementally
                single_res = await self.undo_episode(manifest, ep.episode_path)
                res.restored += single_res.restored
                res.failed += single_res.failed
                res.missing += single_res.missing
                res.conflicts += single_res.conflicts
                # Re-load manifest from disk to get the updated state for the next loop iteration
                runs = await self.list_runs()
                for r in runs:
                    if r.run_id == manifest.run_id:
                        manifest = r
                        break
        return res

    async def undo_run(self, manifest: RunManifest) -> UndoResult:
        """Undo all successful episodes in manifest."""
        res = UndoResult()
        for ep in list(manifest.episodes_processed):
            if ep.status == "success":
                single_res = await self.undo_episode(manifest, ep.episode_path)
                res.restored += single_res.restored
                res.failed += single_res.failed
                res.missing += single_res.missing
                res.conflicts += single_res.conflicts
                # Re-load manifest from disk to get the updated state
                runs = await self.list_runs()
                for r in runs:
                    if r.run_id == manifest.run_id:
                        manifest = r
                        break
        return res

    @staticmethod
    def create_manifest_id() -> str:
        import uuid

        return str(uuid.uuid4())
