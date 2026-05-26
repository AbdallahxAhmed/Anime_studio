from datetime import datetime
from typing import Any
from textual.app import App
from threading import Lock
from src.tui.messages import LogEntry, ProgressUpdate


class LogBridge:
    """A structlog processor that buffers log events and flushes them as Textual messages."""

    def __init__(self, app: App) -> None:
        self.app = app
        self._buffer: list[LogEntry | ProgressUpdate] = []
        self._lock = Lock()

    def __call__(
        self, logger: Any, name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        # Filter INFO+ events
        # structlog level can be in "level" key or via logger method name (name param)
        level = event_dict.get("level") or name or "info"
        level = str(level).lower()

        # If level is debug/trace, ignore it
        if level in ("debug", "trace", "notset"):
            return event_dict

        # Extract timestamp or use current time
        timestamp_raw = event_dict.get("timestamp")
        if isinstance(timestamp_raw, datetime):
            timestamp = timestamp_raw
        elif isinstance(timestamp_raw, str):
            try:
                timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()

        event_text = event_dict.get("event", "")

        # Check for progress context keys
        progress_current = event_dict.get("progress_current")
        progress_total = event_dict.get("progress_total")

        if progress_current is not None or progress_total is not None:
            stage = event_dict.get("stage", "scan")
            try:
                current = (
                    int(progress_current) if progress_current is not None else None
                )
            except (ValueError, TypeError):
                current = None
            try:
                total = int(progress_total) if progress_total is not None else None
            except (ValueError, TypeError):
                total = None

            msg = ProgressUpdate(
                stage=stage,
                current=current,
                total=total,
                label=event_text,
            )
        else:
            # Regular LogEntry
            # Exclude special keys from the context dict
            context = {
                k: v
                for k, v in event_dict.items()
                if k not in ("event", "level", "timestamp", "stage")
            }
            msg = LogEntry(
                timestamp=timestamp,
                level=level,
                event=event_text,
                context=context,
            )

        with self._lock:
            self._buffer.append(msg)

        return event_dict

    def flush(self) -> list[LogEntry | ProgressUpdate]:
        """Posts all buffered messages to the app and returns them."""
        with self._lock:
            messages = list(self._buffer)
            self._buffer.clear()

        for msg in messages:
            self.app.post_message(msg)

        return messages
