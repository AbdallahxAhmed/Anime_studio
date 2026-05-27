from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class ActivityFeedWidget(QWidget):
    """Placeholder ActivityFeedWidget for Foundational phase."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Activity Feed Panel (Placeholder)", self))

    def add_entry(self, log_entry: dict) -> None:
        """Slot to receive log entries from SignalBridge."""
        pass
