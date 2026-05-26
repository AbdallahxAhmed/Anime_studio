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

    def plan_trash_disposal(
        self, timestamp: datetime, max_age_days: int
    ) -> TrashReceipt:
        expiration_time = timestamp + timedelta(days=max_age_days)
        exp_str = expiration_time.strftime("%Y-%m-%d")
        trash_filename = f"EXP-{exp_str}-{self.episode_path.name}"

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
