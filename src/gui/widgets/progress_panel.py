from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class ProgressPanelWidget(QWidget):
    """Placeholder ProgressPanelWidget for Foundational phase."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Progress Panel (Placeholder)", self))

    def update_state(self, state: object) -> None:
        """Slot to receive progress state updates."""
        pass
