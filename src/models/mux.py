from datetime import datetime, timedelta
from pydantic import BaseModel, ConfigDict, Field

from src.models._types import SerializablePath
from src.models.font import FontAsset
from src.models.trash import TrashReceipt


class MuxJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_path: SerializablePath
    subtitle_path: SerializablePath
    fonts: list[FontAsset]
    dry_run: bool = False
    output_path: SerializablePath
    replace_embedded_subtitles: bool = False
    # Track metadata for the new subtitle track (None keeps mkvmerge defaults).
    subtitle_language: str | None = None
    subtitle_track_name: str | None = None
    make_default: bool = False
    # Embedded track being replaced; only this track is dropped when set.
    replaced_track_id: int | None = Field(default=None, ge=0)
    # Subtitle track ids already in the episode (cleared as default when
    # ``make_default`` is set).
    existing_subtitle_track_ids: list[int] = Field(default_factory=list)

    def plan_trash_disposal(
        self, timestamp: datetime, max_age_days: int, run_tag: str | None = None
    ) -> TrashReceipt:
        expiration_time = timestamp + timedelta(days=max_age_days)
        exp_str = expiration_time.strftime("%Y-%m-%d")
        prefix = f"EXP-{exp_str}-{run_tag}" if run_tag else f"EXP-{exp_str}"
        trash_filename = f"{prefix}-{self.episode_path.name}"

        trash_path = self.episode_path.parent / ".anime_studio_trash" / trash_filename

        return TrashReceipt(
            original_path=self.episode_path,
            trash_path=trash_path,
            deletion_time=timestamp,
            expiration_time=expiration_time,
        )


class MuxResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    output_path: SerializablePath
    duration_ms: float = Field(ge=0)
    fonts_attached: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
