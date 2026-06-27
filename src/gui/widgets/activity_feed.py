import logging
from PySide6.QtCore import Signal, Property, QPropertyAnimation
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from typing import Any

logger = logging.getLogger("anime_studio.gui.widgets.activity_feed")


class ActivityFeedWidget(QWidget):
    """Activity feed widget that displays real-time log messages and is collapsible."""

    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_collapsed = True

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Top Control Row
        control_layout = QHBoxLayout()
        
        # Toggle button
        self.toggle_button = QToolButton(self)
        self.toggle_button.setText("▶")
        self.toggle_button.setStyleSheet("border: none; font-weight: bold;")
        self.toggle_button.clicked.connect(self.toggle_collapsed)
        control_layout.addWidget(self.toggle_button)

        self.title_label = QLabel("Activity Log", self)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        control_layout.addWidget(self.title_label)

        # Summary label
        self.summary_label = QLabel(self)
        self.summary_label.setStyleSheet("color: #888888; font-size: 12px;")
        control_layout.addWidget(self.summary_label)

        control_layout.addStretch()

        self.export_button = QPushButton("Export Log", self)
        self.export_button.clicked.connect(self._on_export_click)
        self.export_button.setVisible(False)
        control_layout.addWidget(self.export_button)

        self.clear_button = QPushButton("Clear Feed", self)
        self.clear_button.clicked.connect(self.clear)
        self.clear_button.setVisible(False)
        control_layout.addWidget(self.clear_button)

        layout.addLayout(control_layout)

        # QPlainTextEdit Log Display
        self.log_display = QPlainTextEdit(self)
        self.log_display.setReadOnly(True)
        self.log_display.setUndoRedoEnabled(False)
        self.log_display.document().setMaximumBlockCount(1000)
        self.log_display.setPlaceholderText("Pipeline activity logs will stream here...")
        self.log_display.setVisible(False)
        layout.addWidget(self.log_display)

        self.setMaximumHeight(36)

        logger.info("ActivityFeedWidget initialized as collapsed")

    def toggle_collapsed(self) -> None:
        """Toggle between collapsed and expanded states."""
        self._is_collapsed = not self._is_collapsed
        if self._is_collapsed:
            self.log_display.setVisible(False)
            self.export_button.setVisible(False)
            self.clear_button.setVisible(False)
            self.summary_label.setVisible(True)
            self.setMaximumHeight(36)
            self.toggle_button.setText("▶")
        else:
            self.log_display.setVisible(True)
            self.export_button.setVisible(True)
            self.clear_button.setVisible(True)
            self.summary_label.setVisible(False)
            self.setMaximumHeight(160)
            self.toggle_button.setText("▼")

    def update_summary(self, text: str) -> None:
        """Update the 1-line summary displayed when collapsed."""
        self.summary_label.setText(text)

    def add_entry(self, log_entry: dict[str, Any]) -> None:
        """Slot to receive log entries, color-code, append, and update summary."""
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

        if level in ("error", "critical"):
            color = "#ff5555"
        elif level == "warning":
            color = "#ffaa00"
        elif level == "debug":
            color = "#888888"
        else:
            color = "#e0e0e0"

        html = (
            f'<span style="color: #666666;">{time_tag}</span>'
            f'<span style="color: {color}; font-weight: bold;">{level_tag}</span> '
            f'<span style="color: {color};">{message}</span>'
        )

        v_scroll = self.log_display.verticalScrollBar()
        at_bottom = v_scroll.value() >= v_scroll.maximum() - 5

        self.log_display.appendHtml(html)

        if at_bottom:
            v_scroll.setValue(v_scroll.maximum())

        # Update 1-line summary
        self.update_summary(message)

    def clear(self) -> None:
        """Clear all log entries and clear summary."""
        self.log_display.clear()
        self.update_summary("")
        logger.info("Activity feed cleared")

    def _on_export_click(self) -> None:
        self.export_requested.emit()
