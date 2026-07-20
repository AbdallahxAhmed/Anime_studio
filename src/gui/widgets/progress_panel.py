import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from src.gui.messages import ProgressStage, ProgressState

logger = logging.getLogger("anime_studio.gui.widgets.progress_panel")


class ProgressPanelWidget(QWidget):
    """Widget displaying the pipeline execution progress and status text.

    Supports indeterminate modes (during scans), determinate modes (during muxing),
    and custom green/red visual states on completion or error.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Status Text Label
        self.status_label = QLabel("Idle", self)
        self.status_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(self.status_label)

        # QProgressBar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.progress_bar)

        # Hide by default on start
        self.setVisible(False)
        logger.info("ProgressPanelWidget initialized and hidden by default")

    def update_state(self, state: ProgressState) -> None:
        """Slot to handle ProgressState updates and set styling/visibility."""
        logger.info(f"Progress state update received: stage={state.stage.value}")

        if state.stage == ProgressStage.IDLE:
            self.setVisible(False)

        elif state.stage == ProgressStage.SCANNING:
            self.setVisible(True)
            self.set_status(state.status_text or "Scanning library...")
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setStyleSheet("")

        elif state.stage == ProgressStage.MUXING:
            if state.current is not None and state.total is not None:
                self.set_progress(state.current, state.total)
                self.set_status(
                    state.status_text
                    or f"Muxing episode {state.current} of {state.total}..."
                )
            else:
                self.set_progress(0, 100)
                self.set_status(state.status_text or "Muxing episodes...")

        elif state.stage == ProgressStage.COMPLETE:
            self.set_complete()
            self.set_status(
                state.status_text or "Forensics pipeline completed successfully!"
            )

        elif state.stage == ProgressStage.ERROR:
            self.set_error()
            self.set_status(state.status_text or "Forensics pipeline failed!")

    def set_progress(self, value: int, max_val: int) -> None:
        """Set the determinate range and current value."""
        self.setVisible(True)
        self.progress_bar.setStyleSheet("")
        self.progress_bar.setRange(0, max_val)
        self.progress_bar.setValue(value)

    def set_status(self, text: str) -> None:
        """Set the text displayed in the status label."""
        self.status_label.setText(text)

    def set_complete(self) -> None:
        """Apply green success styling."""
        self.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #4CAF50; border-radius: 4px; text-align: center; }"
            "QProgressBar::chunk { background-color: #4CAF50; }"
        )

    def set_error(self) -> None:
        """Apply red error styling."""
        self.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #F44336; border-radius: 4px; text-align: center; }"
            "QProgressBar::chunk { background-color: #F44336; }"
        )
