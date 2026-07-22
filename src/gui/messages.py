from dataclasses import dataclass
from enum import Enum


from pathlib import Path


class EpisodeStatus(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class EpisodeResult:
    name: str
    episode_path: Path
    status: EpisodeStatus
    fonts_found: int
    fonts_missing: int
    error_summary: str | None = None


@dataclass
class PipelineRunResult:
    episodes: list[EpisodeResult]
    total_duration_seconds: float
    report_path: str
    total_fonts_found: int
    total_fonts_missing: int
    dry_run: bool


@dataclass
class ErrorInfo:
    """Carries structured error context for GUI display.

    Attributes:
        message: Main error message.
        detail: Detailed explanation or traceback.
        is_critical: If True, maps to QMessageBox.critical modal.
            If False, maps to QMessageBox.information/warning.
    """

    message: str
    detail: str | None = None
    is_critical: bool = False


class ProgressStage(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    MUXING = "muxing"
    COMPLETE = "complete"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class ProgressState:
    stage: ProgressStage
    current: int | None = None
    total: int | None = None
    status_text: str = ""
