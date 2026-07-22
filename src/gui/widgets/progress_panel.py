import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from src.gui.messages import ProgressStage, ProgressState
from src.gui.theme import TOKENS, refresh_widget_style

logger = logging.getLogger("anime_studio.gui.widgets.progress_panel")


class ProgressPanelWidget(QWidget):
    """Pipeline progress with semantic success, error, and stopped states."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Pipeline progress")
        self.setAccessibleDescription("Current pipeline status and progress.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            TOKENS.spacing_8,
            TOKENS.spacing_8,
            TOKENS.spacing_8,
            TOKENS.spacing_8,
        )
        layout.setSpacing(TOKENS.spacing_8)

        self.status_label = QLabel("Idle", self)
        self.status_label.setProperty("role", "section-title")
        self.status_label.setAccessibleName("Pipeline status")
        self.status_label.setAccessibleDescription("Idle")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setAccessibleName("Pipeline completion")
        self.progress_bar.setAccessibleDescription("No pipeline is currently running")
        self.progress_bar.setToolTip("Pipeline completion progress")
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setMinimumHeight(TOKENS.control_height)
        self._set_progress_state("default")
        layout.addWidget(self.progress_bar)

        self.setVisible(False)
        logger.info("ProgressPanelWidget initialized and hidden by default")

    def update_state(self, state: ProgressState) -> None:
        """Update visible progress without treating a user stop as an error."""
        logger.info("Progress state update received: stage=%s", state.stage.value)

        if state.stage == ProgressStage.IDLE:
            self._set_progress_state("default")
            self.setVisible(False)
        elif state.stage == ProgressStage.SCANNING:
            self.setVisible(True)
            self._set_progress_state("default")
            self.set_status(state.status_text or "Scanning library...")
            self.progress_bar.setRange(0, 0)
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
        elif state.stage == ProgressStage.STOPPED:
            self.set_stopped()
            self.set_status(state.status_text or "Pipeline stopped")

    def set_progress(self, value: int, max_val: int) -> None:
        """Set determinate progress using the neutral active visual state."""
        self.setVisible(True)
        self._set_progress_state("default")
        self.progress_bar.setRange(0, max_val)
        self.progress_bar.setValue(value)

    def set_status(self, text: str) -> None:
        """Set visible and assistive status text."""
        self.status_label.setText(text)
        self.status_label.setToolTip(text)
        self.status_label.setAccessibleDescription(text)
        self.progress_bar.setAccessibleDescription(text)

    def set_complete(self) -> None:
        """Apply the semantic completed state."""
        self.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self._set_progress_state("success")

    def set_error(self) -> None:
        """Apply the semantic error state."""
        self.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self._set_progress_state("error")

    def set_stopped(self) -> None:
        """Apply a neutral stopped state without implying success or failure."""
        self.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_progress_state("stopped")

    def _set_progress_state(self, state: str) -> None:
        self.progress_bar.setProperty("progressState", state)
        refresh_widget_style(self.progress_bar)
