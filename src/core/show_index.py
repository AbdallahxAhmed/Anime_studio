import asyncio
import tomllib
import logging
from pathlib import Path
from src.models.pipeline import ShowSummary, ShowStatus

logger = logging.getLogger("anime_studio.core.show_index")


class ShowIndexManager:
    """Manages cached show index TOML for instant sidebar population on startup."""

    INDEX_FILE = Path(".anime_studio/show_index.toml")
    CACHE_VERSION = "1.0"

    def __init__(self, base_path: Path) -> None:
        self.base_path = Path(base_path)
        self.index_path = self.base_path / self.INDEX_FILE

    async def load(self) -> list[ShowSummary]:
        """Load shows list from cache TOML file."""
        return await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> list[ShowSummary]:
        if not self.index_path.is_file():
            return []
        try:
            with self.index_path.open("rb") as f:
                data = tomllib.load(f)
            if data.get("cache_version") != self.CACHE_VERSION:
                logger.warning(
                    f"Unsupported cache version: {data.get('cache_version')}"
                )
                return []

            shows = []
            for show_data in data.get("shows", []):
                shows.append(
                    ShowSummary(
                        name=show_data["name"],
                        path=Path(show_data["path"]),
                        status=ShowStatus(show_data["status"]),
                        episode_count=int(show_data["episode_count"]),
                        processed_count=int(show_data["processed_count"]),
                        subtitle_text=show_data["subtitle_text"],
                    )
                )
            return shows
        except Exception as e:
            logger.warning(f"Failed to load show index TOML: {e}")
            return []

    async def save(self, shows: list[ShowSummary]) -> None:
        """Save shows list to cache TOML file."""
        await asyncio.to_thread(self._save_sync, shows)

    def _save_sync(self, shows: list[ShowSummary]) -> None:
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                f'cache_version = "{self.CACHE_VERSION}"',
                "",
            ]
            for show in shows:
                # Convert backslashes for cross-platform compatibility
                toml_path = str(show.path).replace("\\", "/")
                lines.extend(
                    [
                        "[[shows]]",
                        f'name = "{show.name}"',
                        f'path = "{toml_path}"',
                        f'status = "{show.status}"',
                        f"episode_count = {show.episode_count}",
                        f"processed_count = {show.processed_count}",
                        f'subtitle_text = "{show.subtitle_text}"',
                        "",
                    ]
                )

            temp_path = self.index_path.with_suffix(".tmp")
            temp_path.write_text("\n".join(lines), encoding="utf-8")
            if self.index_path.exists():
                self.index_path.unlink()
            temp_path.rename(self.index_path)
        except Exception as e:
            logger.error(f"Failed to save show index TOML: {e}")

    async def add_show(self, show: ShowSummary) -> None:
        """Add a show to index, replacing duplicate by path."""
        shows = await self.load()
        shows = [s for s in shows if s.path != show.path]
        shows.append(show)
        await self.save(shows)

    async def update_status(self, path: Path, status: ShowStatus) -> None:
        """Update ShowStatus for a show matching the given path."""
        shows = await self.load()
        updated = False
        for i, show in enumerate(shows):
            if show.path == path:
                shows[i] = ShowSummary(
                    name=show.name,
                    path=show.path,
                    status=status,
                    episode_count=show.episode_count,
                    processed_count=show.processed_count,
                    subtitle_text=show.subtitle_text,
                )
                updated = True
                break
        if updated:
            await self.save(shows)

    async def remove_show(self, path: Path) -> None:
        """Remove a show from the index by its path."""
        shows = await self.load()
        shows = [s for s in shows if s.path != path]
        await self.save(shows)
