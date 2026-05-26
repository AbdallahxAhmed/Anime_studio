from datetime import datetime
from typing import Any
from textual.message import Message
from src.models.report import PipelineReport


class LogEntry(Message):
    """Represents a single curated log event for the activity feed."""

    def __init__(
        self,
        timestamp: datetime,
        level: str,
        event: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.timestamp = timestamp
        self.level = level
        self.event = event
        self.context = context or {}
        super().__init__()


class ProgressUpdate(Message):
    """Represents a progress update for long-running operations."""

    def __init__(
        self,
        stage: str,
        current: int | None,
        total: int | None,
        label: str,
    ) -> None:
        self.stage = stage
        self.current = current
        self.total = total
        self.label = label
        super().__init__()


class PipelineStarted(Message):
    """Signals transition to execution view."""

    pass


class PipelineCompleted(Message):
    """Signals pipeline run completion with report."""

    def __init__(self, report: PipelineReport, success: bool) -> None:
        self.report = report
        self.success = success
        super().__init__()


class PipelineError(Message):
    """Signals pipeline run error."""

    def __init__(self, error: BaseException, fatal: bool) -> None:
        self.error = error
        self.fatal = fatal
        super().__init__()
