from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class ResultsTableWidget(QWidget):
    """Placeholder ResultsTableWidget for Foundational phase."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Results Table Panel (Placeholder)", self))

    def populate(self, result: object) -> None:
        """Slot to receive pipeline completion results."""
        pass
