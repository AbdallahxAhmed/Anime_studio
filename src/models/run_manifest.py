from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

@dataclass(frozen=True)
class EpisodeProcessed:
    episode_path: str | Path
    trash_receipt_path: str | Path | None = None
    show_name: str = ""
    status: Literal["success", "skipped", "failed"] = "success"

    def __post_init__(self) -> None:
        # Allow passing Path objects, convert to normalized string
        if isinstance(self.episode_path, Path):
            object.__setattr__(self, "episode_path", self.episode_path.as_posix())
        if isinstance(self.trash_receipt_path, Path):
            object.__setattr__(self, "trash_receipt_path", self.trash_receipt_path.as_posix())


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    timestamp: str
    library_path: str | Path
    episodes_processed: Sequence[EpisodeProcessed]

    def __post_init__(self) -> None:
        if isinstance(self.library_path, Path):
            object.__setattr__(self, "library_path", self.library_path.as_posix())
        if not isinstance(self.episodes_processed, tuple):
            object.__setattr__(self, "episodes_processed", tuple(self.episodes_processed))

    @property
    def success_count(self) -> int:
        return sum(1 for e in self.episodes_processed if e.status == "success")

    @property
    def show_names(self) -> list[str]:
        return sorted({e.show_name for e in self.episodes_processed if e.show_name})


@dataclass(frozen=True)
class PipelineCheckpoint:
    library_path: str | Path
    completed_episodes: Sequence[str | Path]
    timestamp: str
    selected_paths: Sequence[str | Path]

    def __post_init__(self) -> None:
        if isinstance(self.library_path, Path):
            object.__setattr__(self, "library_path", self.library_path.as_posix())
        completed = tuple(
            p.as_posix() if isinstance(p, Path) else p for p in self.completed_episodes
        )
        object.__setattr__(self, "completed_episodes", completed)

        selected = tuple(
            p.as_posix() if isinstance(p, Path) else p for p in self.selected_paths
        )
        object.__setattr__(self, "selected_paths", selected)
