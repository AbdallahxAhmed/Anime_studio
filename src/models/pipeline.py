from pydantic import BaseModel, ConfigDict, Field
from src.models._types import SerializablePath
from src.models.font import FontQuery, FontAsset
from src.models.subtitle import SyncResult
from src.models.mux import MuxJob, MuxResult
from src.models.trash import TrashReceipt
from src.models.report import EpisodeStatus


class LibraryScanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_path: SerializablePath
    subtitle_path: SerializablePath
    anime_title: str = Field(min_length=1)


class EpisodeContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    scan_result: LibraryScanResult
    repaired_content: str | None = None
    font_queries: list[FontQuery] = Field(default_factory=list)
    resolved_fonts: list[FontAsset] = Field(default_factory=list)
    missing_fonts: list[str] = Field(default_factory=list)
    sync_result: SyncResult | None = None
    mux_job: MuxJob | None = None
    mux_result: MuxResult | None = None
    trash_receipts: list[TrashReceipt] = Field(default_factory=list)
    status: EpisodeStatus = EpisodeStatus.FAILED
    errors: list[str] = Field(default_factory=list)


class PipelineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    library_path: SerializablePath
    dry_run: bool = False
    sync_enabled: bool = False
    anime_title: str | None = None
