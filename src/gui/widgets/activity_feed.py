import logging
from html import escape
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.gui.theme import TOKENS

logger = logging.getLogger("anime_studio.gui.widgets.activity_feed")


class ActivityFeedWidget(QWidget):
    """Collapsible, keyboard-accessible pipeline activity feed."""

    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_collapsed = True
        self._summary_text = ""
        self.setAccessibleName("Activity log")
        self.setAccessibleDescription(
            "Recent pipeline activity. Expand the panel to read and export the log."
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            TOKENS.spacing_8,
            TOKENS.spacing_8,
            TOKENS.spacing_8,
            TOKENS.spacing_8,
        )
        layout.setSpacing(TOKENS.spacing_8)

        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(TOKENS.spacing_8)

        self.toggle_button = QToolButton(self)
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggle_button.clicked.connect(self.toggle_collapsed)
        control_layout.addWidget(self.toggle_button)

        # Retain the label as an API-compatible semantic heading without duplicating
        # the now-visible toggle label in the compact control row.
        self.title_label = QLabel("Activity Log", self)
        self.title_label.setProperty("role", "section-title")
        self.title_label.setVisible(False)
        control_layout.addWidget(self.title_label)

        self.summary_label = QLabel(self)
        self.summary_label.setProperty("role", "muted")
        self.summary_label.setAccessibleName("Latest activity")
        self.summary_label.setAccessibleDescription("Most recent pipeline event")
        self.summary_label.setWordWrap(False)
        control_layout.addWidget(self.summary_label, 1)

        self.export_button = QPushButton("Export Log", self)
        self.export_button.setAccessibleName("Export activity log")
        self.export_button.setAccessibleDescription(
            "Export the currently retained activity log."
        )
        self.export_button.setToolTip("Export the activity log")
        self.export_button.clicked.connect(self._on_export_click)
        self.export_button.setVisible(False)
        control_layout.addWidget(self.export_button)

        self.clear_button = QPushButton("Clear Feed", self)
        self.clear_button.setAccessibleName("Clear activity feed")
        self.clear_button.setAccessibleDescription(
            "Remove the currently displayed activity entries."
        )
        self.clear_button.setToolTip("Clear all activity entries")
        self.clear_button.clicked.connect(self.clear)
        self.clear_button.setVisible(False)
        control_layout.addWidget(self.clear_button)

        layout.addLayout(control_layout)

        self.log_display = QPlainTextEdit(self)
        self.log_display.setAccessibleName("Activity log entries")
        self.log_display.setAccessibleDescription(
            "Read-only chronological pipeline activity entries."
        )
        self.log_display.setToolTip("Pipeline activity log")
        self.log_display.setReadOnly(True)
        self.log_display.setUndoRedoEnabled(False)
        self.log_display.document().setMaximumBlockCount(1000)
        self.log_display.setPlaceholderText(
            "Pipeline activity logs will stream here..."
        )
        self.log_display.setVisible(False)
        layout.addWidget(self.log_display)

        QWidget.setTabOrder(self.toggle_button, self.log_display)
        QWidget.setTabOrder(self.log_display, self.export_button)
        QWidget.setTabOrder(self.export_button, self.clear_button)
        self._set_collapsed_state(True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render_summary()

    def toggle_collapsed(self) -> None:
        """Toggle between collapsed summary and expanded log states."""
        self._set_collapsed_state(not self._is_collapsed)

    def _set_collapsed_state(self, collapsed: bool) -> None:
        self._is_collapsed = collapsed
        self.log_display.setVisible(not collapsed)
        self.export_button.setVisible(not collapsed)
        self.clear_button.setVisible(not collapsed)
        self.summary_label.setVisible(collapsed)

        if collapsed:
            self.setFixedHeight(TOKENS.activity_collapsed_height)
            self.toggle_button.setText("▶ Activity Log")
            self.toggle_button.setToolTip("Show activity log")
            self.toggle_button.setAccessibleName("Show activity log")
            self.toggle_button.setAccessibleDescription(
                "Activity log is collapsed. Activate to show log entries."
            )
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(TOKENS.activity_expanded_max_height)
            self.toggle_button.setText("▼ Activity Log")
            self.toggle_button.setToolTip("Hide activity log")
            self.toggle_button.setAccessibleName("Hide activity log")
            self.toggle_button.setAccessibleDescription(
                "Activity log is expanded. Activate to show the summary only."
            )

    def update_summary(self, text: str) -> None:
        """Update the one-line summary displayed while collapsed."""
        self._summary_text = text
        self.summary_label.setToolTip(text)
        self.summary_label.setAccessibleDescription(text or "No pipeline activity yet")
        self._render_summary()

    def _render_summary(self) -> None:
        available_width = self.summary_label.width() if self.isVisible() else 1024
        elided = QFontMetrics(self.summary_label.font()).elidedText(
            self._summary_text,
            Qt.TextElideMode.ElideRight,
            available_width,
        )
        self.summary_label.setText(elided)

    def add_entry(self, log_entry: dict[str, Any]) -> None:
        """Append a color-supported, text-labeled activity entry."""
        level = str(log_entry.get("level", "info")).lower()
        message = str(log_entry.get("event", ""))

        if message == "font_ingestion_complete":
            success = log_entry.get("success_count", 0)
            skipped = log_entry.get("skipped_count", 0)
            failed = log_entry.get("failed_count", 0)
            source = str(log_entry.get("source", "unknown"))
            source_display = source.replace("_", " ").title()
            message = (
                f"Font ingestion complete ({source_display}): {success} new, "
                f"{skipped} skipped, {failed} failed"
            )

        timestamp = str(log_entry.get("timestamp", ""))
        time_str = timestamp
        if "T" in timestamp:
            time_str = timestamp.split("T", 1)[1].split(".", 1)[0].rstrip("Z")

        time_tag = f"[{time_str}] " if time_str else ""
        level_tag = f"[{level.upper()}]"
        if level in {"error", "critical"}:
            color = TOKENS.danger
        elif level == "warning":
            color = TOKENS.warning
        elif level == "debug":
            color = TOKENS.activity_debug
        else:
            color = TOKENS.text_primary

        html = (
            f'<span style="color: {TOKENS.activity_timestamp};">{escape(time_tag)}</span>'
            f'<span style="color: {color}; font-weight: bold;">{escape(level_tag)}</span> '
            f'<span style="color: {color};">{escape(message)}</span>'
        )

        vertical_scrollbar = self.log_display.verticalScrollBar()
        at_bottom = vertical_scrollbar.value() >= vertical_scrollbar.maximum() - 5
        self.log_display.appendHtml(html)
        if at_bottom:
            vertical_scrollbar.setValue(vertical_scrollbar.maximum())

        self.update_summary(message)

    def clear(self) -> None:
        """Clear all retained log entries and the collapsed summary."""
        self.log_display.clear()
        self.update_summary("")
        logger.info("Activity feed cleared")

    def _on_export_click(self) -> None:
        self.export_requested.emit()
