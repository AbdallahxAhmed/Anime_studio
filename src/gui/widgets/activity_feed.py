import logging
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("anime_studio.gui.widgets.activity_feed")


class ActivityFeedWidget(QWidget):
    """Activity feed widget that displays real-time log messages.

    Exclusively uses QPlainTextEdit for high-volume logs with maximum size capping,
    color-coded log levels, and auto-scrolling. It is read-only and includes a Clear button.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Top Control Row
        control_layout = QHBoxLayout()
        self.title_label = QLabel("Activity Feed", self)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        control_layout.addWidget(self.title_label)

        control_layout.addStretch()

        self.clear_button = QPushButton("Clear Feed", self)
        self.clear_button.clicked.connect(self.clear)
        control_layout.addWidget(self.clear_button)

        layout.addLayout(control_layout)

        # QPlainTextEdit Log Display
        self.log_display = QPlainTextEdit(self)
        self.log_display.setReadOnly(True)
        self.log_display.setUndoRedoEnabled(False)
        # Cap document size to prevent memory leak
        self.log_display.document().setMaximumBlockCount(1000)
        self.log_display.setPlaceholderText(
            "Pipeline activity logs will stream here..."
        )
        layout.addWidget(self.log_display)

        logger.info("ActivityFeedWidget initialized with QPlainTextEdit display")

    def add_entry(self, log_entry: dict) -> None:
        """Slot to receive log entries, color-code, append, and auto-scroll.

        Handles INFO, WARNING, ERROR/CRITICAL, and DEBUG levels using basic HTML tags.
        """
        level = str(log_entry.get("level", "info")).lower()
        message = log_entry.get("event", "")

        if message == "font_ingestion_complete":
            success = log_entry.get("success_count", 0)
            skipped = log_entry.get("skipped_count", 0)
            failed = log_entry.get("failed_count", 0)
            source = log_entry.get("source", "unknown")
            source_display = source.replace("_", " ").title()
            message = f"Font ingestion complete ({source_display}): {success} new, {skipped} skipped, {failed} failed"

        timestamp = log_entry.get("timestamp", "")

        # Format ISO timestamp to hh:mm:ss if possible
        if timestamp and "T" in timestamp:
            try:
                time_part = timestamp.split("T")[1]
                time_str = time_part.split(".")[0].rstrip("Z")
            except Exception:
                time_str = timestamp
        else:
            time_str = timestamp

        time_tag = f"[{time_str}] " if time_str else ""
        level_tag = f"[{level.upper()}]"

        # Color mapping based on rules
        if level in ("error", "critical"):
            color = "#ff5555"  # Red
        elif level == "warning":
            color = "#ffaa00"  # Yellow/Orange
        elif level == "debug":
            color = "#888888"  # Gray
        else:
            color = "#e0e0e0"  # Default light gray/white for INFO

        # Form lightweight basic HTML using span styles
        html = (
            f'<span style="color: #666666;">{time_tag}</span>'
            f'<span style="color: {color}; font-weight: bold;">{level_tag}</span> '
            f'<span style="color: {color};">{message}</span>'
        )

        # Get vertical scrollbar state before appending
        v_scroll = self.log_display.verticalScrollBar()
        at_bottom = v_scroll.value() >= v_scroll.maximum() - 5

        # Append using appendHtml (supported efficiently by QPlainTextEdit)
        self.log_display.appendHtml(html)

        # Auto-scroll if user was at the bottom
        if at_bottom:
            v_scroll.setValue(v_scroll.maximum())

    def clear(self) -> None:
        """Clear all log entries from the display."""
        self.log_display.clear()
        logger.info("Activity feed cleared")
