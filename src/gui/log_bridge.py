from typing import Any
from PySide6.QtCore import QObject, Signal


class GuiLogBridge(QObject):
    """structlog processor that captures INFO+ events and emits a Qt Signal.

    This replaces the legacy asyncio.Queue implementation to achieve clean,
    thread-safe presentation coupling using native Qt signals and slots.
    """

    log_received = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._session_buffer: list[dict[str, Any]] = []
        self._buffer_cap: int = 10000

    def __call__(
        self,
        logger: Any,
        method_name: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """Intercept, copy, and emit the event; never consume or modify original."""
        level = str(event_dict.get("level", "debug")).lower()
        if level in ("info", "warning", "error", "critical"):
            # Copy event_dict to prevent post-interception mutations
            event_copy = event_dict.copy()

            # Ensure the level is explicitly stored as a string
            event_copy["level"] = level

            # Emit the Qt Signal. Qt guarantees thread safety and event loop delivery.
            self.log_received.emit(event_copy)

            if len(self._session_buffer) < self._buffer_cap:
                self._session_buffer.append(event_copy)

        return event_dict  # pass through to remaining processors

    def get_session_log(self) -> list[dict[str, Any]]:
        return list(self._session_buffer)

    def get_session_entries(self) -> list[dict[str, Any]]:
        return list(self._session_buffer)
