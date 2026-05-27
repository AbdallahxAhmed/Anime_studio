import logging
from typing import Any
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QSplitter,
    QMessageBox,
    QPushButton,
)

from src.gui.signals import SignalBridge
from src.gui.widgets import (
    LibraryPickerWidget,
    ActivityFeedWidget,
    ProgressPanelWidget,
    ResultsTableWidget,
)

logger = logging.getLogger("anime_studio.gui.main_window")


class MainWindow(QMainWindow):
    """The primary QMainWindow for the Anime Studio dashboard.

    Houses the configuration/picker panel, the real-time activity feed,
    the progress panel, and the pipeline results table.
    """

    def __init__(
        self,
        pipeline_runner: Any,
        log_bridge: Any,
        config: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pipeline_runner = pipeline_runner
        self.config = config
        self._pipeline_running = False

        # Initialize SignalBridge
        self.signal_bridge = SignalBridge()

        # Set window properties
        self.setWindowTitle("Anime Studio v3 - Forensics Dashboard")
        self.resize(1100, 800)
        self.setMinimumSize(800, 600)

        # Central Widget & Main Layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Main splitter (horizontal) to separate inputs/logs from status/results
        splitter = QSplitter(Qt.Orientation.Horizontal, central_widget)
        main_layout.addWidget(splitter)

        # Left panel: Library Picker + Activity Feed
        left_widget = QWidget(splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Config Panel (Library Picker + Run Button)
        config_group = QWidget(left_widget)
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(5)

        self.library_picker = LibraryPickerWidget(config_group)
        config_layout.addWidget(self.library_picker)

        self.run_button = QPushButton("Run Pipeline", config_group)
        self.run_button.setEnabled(False)
        config_layout.addWidget(self.run_button)

        left_layout.addWidget(config_group)

        self.activity_feed = ActivityFeedWidget(left_widget)
        left_layout.addWidget(self.activity_feed)
        splitter.addWidget(left_widget)

        # Right panel: Progress Panel + Results Table
        right_widget = QWidget(splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.progress_panel = ProgressPanelWidget(right_widget)
        self.results_table = ResultsTableWidget(right_widget)

        right_layout.addWidget(self.progress_panel)
        right_layout.addWidget(self.results_table)
        splitter.addWidget(right_widget)

        # Set initial splitter sizes (roughly 45% left, 55% right)
        splitter.setSizes([450, 550])

        # Wire thread-safe log bridge signals directly to slots
        log_bridge.log_received.connect(self.signal_bridge.log_received)

        # Connect SignalBridge slots to corresponding widgets
        self.signal_bridge.log_received.connect(self.activity_feed.add_entry)
        self.signal_bridge.progress_updated.connect(self.progress_panel.update_state)
        self.signal_bridge.pipeline_finished.connect(self.results_table.populate)
        self.signal_bridge.result_added.connect(self.results_table.add_episode_result)

        # Wire library picker selection event to path handler
        self.library_picker.library_selected.connect(self._on_library_selected)

        logger.info("MainWindow initialized and signal bridge wired")

    def _on_library_selected(self, path: str) -> None:
        """Handle library folder selection by updating configuration and UI state."""
        self.config.library_path = Path(path)
        self.config.save_to_toml()
        self.run_button.setEnabled(True)
        logger.info(f"Library path configured and saved: {path}")

    def closeEvent(self, event: Any) -> None:
        """Override close event to confirm exit if pipeline is active."""
        if self._pipeline_running:
            reply = QMessageBox.question(
                self,
                "Pipeline Active",
                "A forensics pipeline is currently running. Closing the application will abort the process. "
                "Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                logger.info("Application closed by user during pipeline run; aborting")
                event.accept()
            else:
                event.ignore()
        else:
            logger.info("Application closing gracefully")
            event.accept()
