import importlib
import logging
from typing import Any
from pathlib import Path
from qasync import asyncSlot
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
        font_ingestion_service: Any,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pipeline_runner = pipeline_runner
        self.config = config
        self.font_ingestion_service = font_ingestion_service
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

        self.import_button = QPushButton("Import Fonts", config_group)
        config_layout.addWidget(self.import_button)

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
        self.signal_bridge.log_received.connect(self._on_log_received)
        self.signal_bridge.progress_updated.connect(self.progress_panel.update_state)
        self.signal_bridge.pipeline_finished.connect(self.results_table.populate)
        self.signal_bridge.result_added.connect(self.results_table.add_episode_result)

        # Wire library picker selection event to path handler
        self.library_picker.library_selected.connect(self._on_library_selected)

        # Wire import button click
        self.import_button.clicked.connect(self._on_import_fonts_click)

        # Wire run button click
        self.run_button.clicked.connect(self._on_run_click)

        # Setup Drag & Drop
        self.setAcceptDrops(True)
        self._default_style = self.styleSheet()

        logger.info("MainWindow initialized and signal bridge wired")

    def _on_library_selected(self, path: str) -> None:
        """Handle library folder selection by updating configuration and UI state."""
        p = Path(path)
        if p.is_dir():
            self.config.library_path = p
            self.config.save_to_toml()
            self.run_button.setEnabled(True)
            logger.info(f"Library path configured and saved: {path}")
        else:
            self.run_button.setEnabled(False)
            logger.warning(f"Inaccessible library path selected: {path}")

    @asyncSlot()
    async def _on_run_click(self) -> None:
        """Trigger the forensics pipeline runner asynchronously without blocking the UI thread."""
        library_path = self.library_picker.get_path()
        if not library_path:
            QMessageBox.warning(
                self,
                "No Library Selected",
                "Please select an anime library directory first.",
            )
            return

        p = Path(library_path)
        if not p.is_dir():
            QMessageBox.critical(
                self, "Invalid Path", "Selected path is not a valid directory."
            )
            return

        # Lock UI controls during active pipeline run
        self._pipeline_running = True
        self.run_button.setEnabled(False)
        self.library_picker.setEnabled(False)
        self.results_table.clear_results()

        from src.gui.messages import ProgressStage, ProgressState
        from src.gui.bootstrap import map_pipeline_report

        pipeline_mod = importlib.import_module("src.models.pipeline")
        PipelineConfig = pipeline_mod.PipelineConfig

        # Initial state update
        self.signal_bridge.progress_updated.emit(
            ProgressState(
                stage=ProgressStage.SCANNING,
                status_text="Initiating library analysis...",
            )
        )

        try:
            config = PipelineConfig(
                library_path=p,
                dry_run=self.config.dry_run
                if hasattr(self.config, "dry_run")
                else False,
                sync_enabled=True,
            )

            # Await the core runner's run method asynchronously on the qasync event loop
            report = await self.pipeline_runner.run(config)

            # Map domain report to UI result structures
            run_result = map_pipeline_report(report, p, config.dry_run)
            self.signal_bridge.pipeline_finished.emit(run_result)

            # Emit final success state
            self.signal_bridge.progress_updated.emit(
                ProgressState(
                    stage=ProgressStage.COMPLETE,
                    status_text="Pipeline executed successfully!",
                )
            )

        except Exception as e:
            logger.error(f"Forensics pipeline execution failed: {e}")
            self.signal_bridge.progress_updated.emit(
                ProgressState(
                    stage=ProgressStage.ERROR, status_text=f"Pipeline failed: {e}"
                )
            )
            self.signal_bridge.pipeline_error.emit(str(e))

            # Display critical error modal
            from src.gui.messages import ErrorInfo
            from src.gui.widgets.error_dialog import show_error_dialog

            err_info = ErrorInfo(
                message="Critical error occurred during pipeline run.",
                detail=str(e),
                is_critical=True,
            )
            show_error_dialog(self, err_info)

        finally:
            self._pipeline_running = False
            self.run_button.setEnabled(True)
            self.library_picker.setEnabled(True)

    def _on_log_received(self, log_entry: dict) -> None:
        """Slot to intercept structured log entries and map them to progress updates."""
        stage_val = log_entry.get("stage")
        if stage_val:
            current = log_entry.get("progress_current")
            total = log_entry.get("progress_total")
            event_msg = log_entry.get("event", "")

            from src.gui.messages import ProgressStage, ProgressState

            if stage_val == "scan":
                state = ProgressState(
                    stage=ProgressStage.SCANNING,
                    current=current,
                    total=total,
                    status_text=event_msg,
                )
                self.signal_bridge.progress_updated.emit(state)
            elif stage_val == "mux":
                state = ProgressState(
                    stage=ProgressStage.MUXING,
                    current=current,
                    total=total,
                    status_text=event_msg,
                )
                self.signal_bridge.progress_updated.emit(state)

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

    @asyncSlot()
    async def _on_import_fonts_click(self) -> None:
        """Handle 'Import Fonts' button click to let users manually select a folder to import."""
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Font Folder to Import",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            logger.info(f"User initiated manual font import from folder: {folder}")
            await self.font_ingestion_service.ingest_directories(
                [Path(folder)], source="manual_import"
            )

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(self._is_valid_font_drop(url) for url in urls):
                event.acceptProposedAction()
                self.setStyleSheet("QMainWindow { border: 3px solid #4CAF50; }")
                return
        event.ignore()

    def dragLeaveEvent(self, event: Any) -> None:
        self.setStyleSheet(self._default_style)

    def dropEvent(self, event: Any) -> None:
        self.setStyleSheet(self._default_style)
        urls = event.mimeData().urls()
        paths = [Path(url.toLocalFile()) for url in urls]
        import asyncio

        asyncio.ensure_future(self._handle_font_drop(paths))
        event.acceptProposedAction()

    def _is_valid_font_drop(self, url: Any) -> bool:
        """Helper to validate if a dropped URL is a directory or font file."""
        local_file = url.toLocalFile()
        if not local_file:
            return False
        p = Path(local_file)
        if p.is_dir():
            return True
        return p.suffix.lower() in (".ttf", ".otf")

    async def _handle_font_drop(self, paths: list[Path]) -> None:
        """Handles font drop async by separating into dirs and files and importing."""
        dirs = [p for p in paths if p.is_dir()]
        files = [
            p for p in paths if p.is_file() and p.suffix.lower() in (".ttf", ".otf")
        ]

        if dirs:
            logger.info("Drag and drop: Ingesting directories", directories=dirs)
            await self.font_ingestion_service.ingest_directories(
                dirs, source="drag_drop"
            )
        if files:
            logger.info("Drag and drop: Ingesting files", files=files)
            await self.font_ingestion_service.ingest_files(files, source="drag_drop")
