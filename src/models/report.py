from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field

from src.models._types import SerializablePath
from src.models.subtitle import SyncResult
from src.models.mux import MuxResult


class EpisodeStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class EpisodeReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_path: SerializablePath
    status: EpisodeStatus
    subtitle_result: SyncResult | None = None
    mux_result: MuxResult | None = None
    missing_fonts: list[str] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)


class PipelineReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_timestamp: datetime
    duration_ms: float = Field(ge=0)
    anime_title: str
    episodes: list[EpisodeReport]
    total_fonts_found: int = Field(ge=0)
    genuine_misses: list[str] = Field(default_factory=list)
