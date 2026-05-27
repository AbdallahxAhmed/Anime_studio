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
        if not isinstance(state, ProgressState):
            logger.warning(f"Invalid progress state format received: {type(state)}")
            return

        logger.info(f"Progress state update received: stage={state.stage.value}")

        if state.stage == ProgressStage.IDLE:
            self.setVisible(False)

        elif state.stage == ProgressStage.SCANNING:
            self.setVisible(True)
            self.status_label.setText(state.status_text or "Scanning library...")
            # Set to indeterminate mode (min=0, max=0)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setStyleSheet("")

        elif state.stage == ProgressStage.MUXING:
            self.setVisible(True)
            self.progress_bar.setStyleSheet("")
            if state.current is not None and state.total is not None:
                self.progress_bar.setRange(0, state.total)
                self.progress_bar.setValue(state.current)
                self.status_label.setText(
                    state.status_text
                    or f"Muxing episode {state.current} of {state.total}..."
                )
            else:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(0)
                self.status_label.setText(state.status_text or "Muxing episodes...")

        elif state.stage == ProgressStage.COMPLETE:
            self.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.status_label.setText(
                state.status_text or "Forensics pipeline completed successfully!"
            )
            # Premium Green styling for complete status
            self.progress_bar.setStyleSheet(
                "QProgressBar { border: 1px solid #4CAF50; border-radius: 4px; text-align: center; }"
                "QProgressBar::chunk { background-color: #4CAF50; }"
            )

        elif state.stage == ProgressStage.ERROR:
            self.setVisible(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.status_label.setText(state.status_text or "Forensics pipeline failed!")
            # Premium Red styling for error status
            self.progress_bar.setStyleSheet(
                "QProgressBar { border: 1px solid #F44336; border-radius: 4px; text-align: center; }"
                "QProgressBar::chunk { background-color: #F44336; }"
            )
