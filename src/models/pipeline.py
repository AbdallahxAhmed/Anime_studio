from pydantic import BaseModel, ConfigDict, Field
from src.models._types import SerializablePath
from src.models.font import FontQuery, FontAsset
from src.models.subtitle import SubtitleSource, SyncResult
from src.models.mux import MuxJob, MuxResult
from src.models.trash import TrashReceipt
from src.models.report import EpisodeStatus


class EmbeddedTrack(BaseModel):
    """One embedded ASS/SSA subtitle track inside an MKV."""

    model_config = ConfigDict(frozen=True)

    track_id: int = Field(ge=0)
    language: str = ""          # ISO 639-2/B e.g. "ara", "eng"
    language_ietf: str = ""     # BCP 47 e.g. "ar", "en"
    is_default: bool = False
    codec: str = ""             # e.g. "SubStationAlpha"


class EmbeddedSubInfo(BaseModel):
    """Metadata about embedded ASS subtitle tracks inside an MKV container."""

    model_config = ConfigDict(frozen=True)

    tracks: list[EmbeddedTrack] = Field(default_factory=list)
    has_embedded_fonts: bool = False
    embedded_font_names: list[str] = Field(default_factory=list)

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def languages(self) -> list[str]:
        return [t.language for t in self.tracks if t.language]


class LibraryScanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    episode_path: SerializablePath
    subtitle_path: SerializablePath | None = None
    subtitle_source: SubtitleSource = SubtitleSource.EXTERNAL
    anime_title: str = Field(min_length=1)
    embedded_sub_info: EmbeddedSubInfo | None = None


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


class LibraryScanOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    episodes: list[LibraryScanResult]
    font_directories: list[SerializablePath] = Field(default_factory=list)
