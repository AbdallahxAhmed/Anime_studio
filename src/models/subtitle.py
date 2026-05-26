from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from src.models._types import SerializablePath
from src.models.trash import TrashReceipt


class AssetLifecycle(str, Enum):
    ORIGINAL = "ORIGINAL"
    REPAIRED = "REPAIRED"
    SYNCED = "SYNCED"
    TRASHED = "TRASHED"


class SubtitleFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: SerializablePath
    encoding_detected: str
    encoding_source: str
    line_ending: str
    fonts_required: list[str]
    lifecycle: AssetLifecycle = AssetLifecycle.ORIGINAL

    def plan_trash_disposal(
        self, timestamp: datetime, max_age_days: int
    ) -> TrashReceipt:
        expiration_time = timestamp + timedelta(days=max_age_days)
        exp_str = expiration_time.strftime("%Y-%m-%d")
        trash_filename = f"EXP-{exp_str}-{self.path.name}"

        trash_path = self.path.parent / ".anime_studio_trash" / trash_filename

        return TrashReceipt(
            original_path=self.path,
            trash_path=trash_path,
            deletion_time=timestamp,
            expiration_time=expiration_time,
        )


class SyncResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    tool_used: str
    tool_fallback_used: str | None = None
    offset_ms: float
    duration_ms: float = Field(ge=0)
