from __future__ import annotations
import asyncio
import importlib
import logging
from typing import Any, TYPE_CHECKING
from pathlib import Path
from qasync import asyncSlot

if TYPE_CHECKING:
    from src.models.run_manifest import RunManifest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QMessageBox,
    QPushButton,
    QLabel,
    QFileDialog,
)

from src.errors import AnimeStudioError
from src.gui.signals import SignalBridge
from src.gui.widgets import (
    ActivityFeedWidget,
    ProgressPanelWidget,
    ResultsTableWidget,
    ShowSidebarWidget,
    EpisodeTableWidget,
)
from src.models.pipeline import ShowSummary, ShowStatus

logger = logging.getLogger("anime_studio.gui.main_window")


class MainWindow(QMainWindow):
    """The primary QMainWindow for the Anime Studio dashboard.

    Houses the horizontal two-panel layout featuring the ShowSidebarWidget
    on the left and the main control panel with EpisodeTableWidget on the right.
    """

    def __init__(
        self,
        pipeline_runner: Any,
        log_bridge: Any,
        config: Any,
        font_ingestion_service: Any,
        show_index_manager: Any,
        checkpoint_manager: Any = None,
        undo_service: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pipeline_runner = pipeline_runner
        self._log_bridge = log_bridge
        self.config = config
        self.font_ingestion_service = font_ingestion_service
        self._show_index = show_index_manager
        self._checkpoint_manager = checkpoint_manager
        self._undo_service = undo_service
        self._pipeline_running = False
        self._is_refreshing = False
        self._awaiting_selection = False
        self._pending_scan_output = None
        self._stop_event: asyncio.Event | None = None

        # Initialize SignalBridge
        self.signal_bridge = SignalBridge()

        # Set window properties
        self.setWindowTitle("Anime Studio v3 - Forensics Dashboard")
        self.resize(1100, 800)
        self.setMinimumSize(800, 600)

        # Central Widget & Main Layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Root layout (vertical)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # Header Bar (44px fixed height)
        self._header_bar = QWidget(central_widget)
        self._header_bar.setFixedHeight(44)
        header_layout = QHBoxLayout(self._header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)

        app_title = QLabel("Anime Studio", self._header_bar)
        app_title.setStyleSheet("font-weight: bold; font-size: 16px;")
        header_layout.addWidget(app_title)

        # Read-only library path label
        lib_path_str = (
            str(self.config.library_path)
            if self.config.library_path
            else "No Library Path Configured"
        )
        self.library_path_label = QLabel(lib_path_str, self._header_bar)
        self.library_path_label.setStyleSheet(
            "color: #888888; font-style: italic; font-size: 13px;"
        )
        header_layout.addWidget(self.library_path_label)
        header_layout.addStretch()

        # Settings button
        self.settings_btn = QPushButton("⚙ Settings", self._header_bar)
        header_layout.addWidget(self.settings_btn)

        root_layout.addWidget(self._header_bar)

        # Main splitter (horizontal)
        splitter = QSplitter(Qt.Orientation.Horizontal, central_widget)
        root_layout.addWidget(splitter)

        # Left panel: ShowSidebarWidget
        self._sidebar = ShowSidebarWidget(self.signal_bridge, splitter)
        splitter.addWidget(self._sidebar)

        # Right panel: MainPanel (vertical)
        main_panel = QWidget(splitter)
        main_panel_layout = QVBoxLayout(main_panel)
        main_panel_layout.setContentsMargins(0, 0, 0, 0)
        main_panel_layout.setSpacing(10)

        # Show Header Bar (56px)
        self._show_header = QWidget(main_panel)
        self._show_header.setFixedHeight(56)
        show_header_layout = QHBoxLayout(self._show_header)
        show_header_layout.setContentsMargins(0, 0, 0, 0)

        self._show_name_label = QLabel("Select a show to start", self._show_header)
        self._show_name_label.setStyleSheet("font-weight: bold; font-size: 18px;")
        show_header_layout.addWidget(self._show_name_label)

        self._show_subtitle_label = QLabel("", self._show_header)
        self._show_subtitle_label.setStyleSheet("color: #888888; font-size: 13px;")
        show_header_layout.addWidget(self._show_subtitle_label)

        show_header_layout.addStretch()

        self.undo_button = QPushButton("Undo", self._show_header)
        show_header_layout.addWidget(self.undo_button)

        self.stop_button = QPushButton("Stop", self._show_header)
        self.stop_button.setVisible(False)
        show_header_layout.addWidget(self.stop_button)

        self.run_button = QPushButton("Run 0 selected", self._show_header)
        self.run_button.setEnabled(False)
        show_header_layout.addWidget(self.run_button)

        main_panel_layout.addWidget(self._show_header)

        # Episode Table Widget
        self._episode_table = EpisodeTableWidget(main_panel)
        main_panel_layout.addWidget(self._episode_table)

        # Progress Panel Widget
        self.progress_panel = ProgressPanelWidget(main_panel)
        main_panel_layout.addWidget(self.progress_panel)

        # Activity Feed Widget (collapsible)
        self.activity_feed = ActivityFeedWidget(main_panel)
        main_panel_layout.addWidget(self.activity_feed)

        # Results table
        self.results_table = ResultsTableWidget(main_panel)
        self.results_table.setVisible(False)
        main_panel_layout.addWidget(self.results_table)

        splitter.addWidget(main_panel)

        # Set initial splitter sizes (220px fixed for sidebar, rest for main panel)
        splitter.setSizes([220, 880])

        # Wire thread-safe log bridge signals directly to slots
        log_bridge.log_received.connect(self.signal_bridge.log_received)

        # Connect SignalBridge slots to corresponding widgets
        self.signal_bridge.log_received.connect(self.activity_feed.add_entry)
        self.signal_bridge.log_received.connect(self._on_log_received)
        self.signal_bridge.progress_updated.connect(self.progress_panel.update_state)
        self.signal_bridge.pipeline_finished.connect(self.results_table.populate)
        self.signal_bridge.result_added.connect(self.results_table.add_episode_result)

        # Wire new sidebar widgets signals
        self._sidebar.show_selected.connect(self._on_show_selected)
        self._sidebar.add_folder_requested.connect(self._on_add_folder)
        self._sidebar.refresh_requested.connect(self._on_refresh_index)

        # Wire Episode Table selection changes
        self._episode_table.selection_changed.connect(self._on_selection_changed)

        # Wire settings button to import click
        self.settings_btn.clicked.connect(self._on_import_fonts_click)

        # Wire actions
        self.run_button.clicked.connect(self._on_run_click)
        self.stop_button.clicked.connect(self._on_stop_click)
        self.undo_button.clicked.connect(self._on_undo_click)
        self.activity_feed.export_requested.connect(self._on_export_log)

        # Setup Drag & Drop
        self.setAcceptDrops(True)
        self._default_style = self.styleSheet()

        logger.info("MainWindow initialized and signal bridge wired")

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_startup(self) -> None:
        """Loads index on startup and populates sidebar."""
        shows = await self._show_index.load()
        self._sidebar.populate(shows)

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_refresh_index(self) -> None:
        """Full refresh scan of config.library_path."""
        if self._is_refreshing:
            logger.info("Refresh already in progress, ignoring duplicate request")
            return

        library_path = self.config.library_path
        if not library_path:
            return

        self._is_refreshing = True
        self._sidebar.set_refresh_enabled(False)
        from datetime import datetime

        self.signal_bridge.log_received.emit(
            {
                "event": f"Starting full library rescan for {library_path}...",
                "level": "info",
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.progress_panel.set_status("Scanning full library...")
        self.progress_panel.setVisible(True)
        self.progress_panel.progress_bar.setRange(0, 0)

        try:
            scan_output = await self.pipeline_runner.library_scanner.scan(
                Path(library_path)
            )
            shows = []
            for node in scan_output.show_tree:
                shows.append(
                    ShowSummary(
                        name=node.name,
                        path=node.path,
                        status=ShowStatus.READY
                        if node.total_count > 0
                        else ShowStatus.NO_SUBTITLE,
                        episode_count=node.total_count,
                        processed_count=0,
                        subtitle_text=f"{node.total_count} episodes found",
                    )
                )
            self._sidebar.populate(shows)
            await self._show_index.save(shows)
            self.progress_panel.setVisible(False)
            self.signal_bridge.log_received.emit(
                {
                    "event": f"Library rescan completed: {len(shows)} shows found.",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except (AnimeStudioError, OSError) as e:
            logger.error(f"Refresh failed: {e}")
            self.progress_panel.set_error()
            self.progress_panel.set_status(f"Refresh failed: {e}")
            self.signal_bridge.log_received.emit(
                {
                    "event": f"Library rescan failed: {e}",
                    "level": "error",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        finally:
            self._is_refreshing = False
            self._sidebar.set_refresh_enabled(True)

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_show_selected(self, name: str, path: Path) -> None:
        """Load episodes for selected show into EpisodeTableWidget."""
        self._current_show_name = name
        self._current_show_path = Path(path)
        self._show_name_label.setText(name)

        self.progress_panel.set_status("Scanning folder...")
        self.progress_panel.setVisible(True)
        self.progress_panel.progress_bar.setRange(0, 0)

        try:
            episodes = await self.pipeline_runner.library_scanner.scan_folder(
                Path(path)
            )
            self._episode_table.populate(episodes.episodes)
            self._show_subtitle_label.setText(
                f" ({len(episodes.episodes)} episodes found)"
            )
            self.run_button.setText("Run 0 selected")
            self.run_button.setEnabled(False)
            self.progress_panel.setVisible(False)
        except (AnimeStudioError, OSError) as e:
            logger.error(f"Failed to scan folder: {e}")
            self.progress_panel.set_error()
            self.progress_panel.set_status(f"Scan failed: {e}")

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_add_folder(self, path: Path | None = None) -> None:
        """Open folder dialog or accept path, scan, add to sidebar."""
        if path is None:
            folder = QFileDialog.getExistingDirectory(
                self, "Select Show Folder to Add", ""
            )
            if not folder:
                return
            path = Path(folder)
        else:
            path = Path(path)

        self.progress_panel.set_status(f"Adding show: {path.name}...")
        self.progress_panel.setVisible(True)
        self.progress_panel.progress_bar.setRange(0, 0)

        try:
            result = await self.pipeline_runner.library_scanner.scan_folder(path)
            status = ShowStatus.READY if result.episodes else ShowStatus.NO_SUBTITLE
            summary = ShowSummary(
                name=path.name,
                path=path,
                status=status,
                episode_count=len(result.episodes),
                processed_count=0,
                subtitle_text=f"{len(result.episodes)} episodes found",
            )
            self._sidebar.add_show(summary)
            await self._show_index.add_show(summary)
            self.progress_panel.setVisible(False)
        except (AnimeStudioError, OSError) as e:
            logger.error(f"Failed to add folder: {e}")
            self.progress_panel.set_error()
            self.progress_panel.set_status(f"Failed to add folder: {e}")

    def _on_selection_changed(self, paths: list[Path]) -> None:
        count = len(paths)
        self.run_button.setText(f"Run {count} selected")
        self.run_button.setEnabled(count > 0)

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_run_click(self) -> None:
        """Trigger the forensics pipeline runner asynchronously without blocking the UI thread."""
        library_path = self.config.library_path or (
            self._current_show_path.parent
            if hasattr(self, "_current_show_path")
            else None
        )
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

        from src.gui.messages import ProgressStage, ProgressState
        from src.gui.bootstrap import map_pipeline_report

        pipeline_mod = importlib.import_module("src.models.pipeline")
        PipelineConfig = pipeline_mod.PipelineConfig

        # Lock UI controls during active pipeline run
        self._pipeline_running = True
        self.run_button.setEnabled(False)
        self.undo_button.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.stop_button.setVisible(True)
        self.stop_button.setEnabled(True)
        self.stop_button.setText("Stop")
        self.results_table.clear_results()

        # Update show status to processing in sidebar/index
        if hasattr(self, "_current_show_path"):
            self._sidebar.update_show_status(
                self._current_show_path, ShowStatus.PROCESSING
            )
            await self._show_index.update_status(
                self._current_show_path, ShowStatus.PROCESSING
            )

        self.signal_bridge.progress_updated.emit(
            ProgressState(
                stage=ProgressStage.SCANNING,
                status_text="Executing pipeline...",
            )
        )

        self._stop_event = asyncio.Event()

        try:
            # Gather selected paths from EpisodeTableWidget
            selected = self._episode_table.get_selected_paths()

            config = PipelineConfig(
                library_path=p,
                dry_run=self.config.dry_run
                if hasattr(self.config, "dry_run")
                else False,
                sync_enabled=True,
                selected_paths=frozenset(selected) if selected else None,
            )

            report = await self.pipeline_runner.run(
                config,
                stop_event=self._stop_event,
                checkpoint_manager=self._checkpoint_manager,
                undo_service=self._undo_service,
            )

            run_result = map_pipeline_report(report, p, config.dry_run)
            self.signal_bridge.pipeline_finished.emit(run_result)

            # Update statuses on completion
            final_status = ShowStatus.ALL_DONE
            for ep_res in run_result.episodes:
                status_str = (
                    ep_res.status.value
                    if hasattr(ep_res.status, "value")
                    else str(ep_res.status)
                )
                self._episode_table.update_episode_status(
                    ep_res.episode_path, status_str
                )
                if status_str.lower() in ("failed", "error"):
                    final_status = ShowStatus.WARNING

            if hasattr(self, "_current_show_path"):
                self._sidebar.update_show_status(self._current_show_path, final_status)
                await self._show_index.update_status(
                    self._current_show_path, final_status
                )

            if self._stop_event.is_set():
                self.signal_bridge.progress_updated.emit(
                    ProgressState(
                        stage=ProgressStage.COMPLETE,
                        status_text="Pipeline stopped by user. Checkpoint saved.",
                    )
                )
            else:
                self.signal_bridge.progress_updated.emit(
                    ProgressState(
                        stage=ProgressStage.COMPLETE,
                        status_text="Pipeline executed successfully!",
                    )
                )

        except (AnimeStudioError, OSError, ValueError, RuntimeError) as e:
            logger.error(f"Forensics pipeline execution failed: {e}")
            self.signal_bridge.progress_updated.emit(
                ProgressState(
                    stage=ProgressStage.ERROR, status_text=f"Pipeline failed: {e}"
                )
            )
            self.signal_bridge.pipeline_error.emit(str(e))

            if hasattr(self, "_current_show_path"):
                self._sidebar.update_show_status(
                    self._current_show_path, ShowStatus.WARNING
                )
                await self._show_index.update_status(
                    self._current_show_path, ShowStatus.WARNING
                )

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
            self._stop_event = None
            self.stop_button.setVisible(False)
            self.run_button.setEnabled(True)
            self.undo_button.setEnabled(True)
            self.settings_btn.setEnabled(True)

    def _on_stop_click(self) -> None:
        """Handle Stop button click by setting the stop event."""
        if self._stop_event:
            self._stop_event.set()
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Stopping...")

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_undo_click(self) -> None:
        """Open the Undo dialog and run the selected undo action."""
        if not self._undo_service:
            return
        library_path = self.config.library_path or (
            self._current_show_path.parent
            if hasattr(self, "_current_show_path")
            else None
        )
        if not library_path:
            QMessageBox.warning(self, "No Library", "Select a library first.")
            return

        manifests = await self._undo_service.list_runs()
        if not manifests:
            QMessageBox.information(self, "No History", "No pipeline runs to undo.")
            return

        from src.gui.widgets.undo_dialog import UndoDialog

        dialog = UndoDialog(self)
        dialog.populate(manifests)

        dialog.undo_requested.connect(
            lambda r: asyncio.ensure_future(self._execute_undo(manifests, r))
        )
        dialog.exec()

    async def _execute_undo(
        self, manifests: list[RunManifest], result: dict[str, Any]
    ) -> None:
        idx = result["manifest_index"]
        manifest = manifests[idx]
        level = result["level"]

        self.undo_button.setEnabled(False)

        try:
            if level == "full":
                undo_res = await self._undo_service.undo_run(manifest)
            elif level == "show":
                show_name = result["show_names"][0] if result.get("show_names") else ""
                undo_res = await self._undo_service.undo_show(manifest, show_name)
            else:
                ep_name = (
                    result["episode_names"][0] if result.get("episode_names") else ""
                )
                target_path = None
                for ep in manifest.episodes_processed:
                    if Path(ep.episode_path).name == ep_name:
                        target_path = ep.episode_path
                        break
                if target_path:
                    undo_res = await self._undo_service.undo_episode(
                        manifest, target_path
                    )
                else:
                    undo_service_mod = importlib.import_module("src.core.undo_service")
                    UndoResult = undo_service_mod.UndoResult
                    undo_res = UndoResult(failed=1)

            msg = (
                f"Undo completed.\n\n"
                f"Restored: {undo_res.restored}\n"
                f"Conflicts: {undo_res.conflicts}\n"
                f"Missing: {undo_res.missing}\n"
                f"Failed: {undo_res.failed}"
            )
            QMessageBox.information(self, "Undo Result", msg)

            from datetime import datetime

            self.signal_bridge.log_received.emit(
                {
                    "event": f"Undo completed. Restored: {undo_res.restored}, Conflicts: {undo_res.conflicts}, Missing: {undo_res.missing}",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except (AnimeStudioError, OSError, ValueError, KeyError) as e:
            logger.error(f"Undo operation failed: {e}")
            QMessageBox.critical(self, "Undo Failed", f"Operation failed: {e}")
        finally:
            self.undo_button.setEnabled(True)

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_export_log(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from datetime import datetime

        entries = self._log_bridge.get_session_log()
        if not entries:
            self.signal_bridge.log_received.emit(
                {
                    "event": "No log data to export",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            return

        default_name = f"anime_studio_{datetime.now():%Y-%m-%d_%H-%M}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Log",
            str(Path.home() / default_name),
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        try:
            log_export_mod = importlib.import_module("src.core.log_export")
            await log_export_mod.export_log_to_file(entries, Path(path))
            self.signal_bridge.log_received.emit(
                {
                    "event": f"Log exported to {path}",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except OSError as e:
            self.signal_bridge.log_received.emit(
                {
                    "event": f"Log export failed: {e}",
                    "level": "error",
                    "timestamp": datetime.now().isoformat(),
                }
            )

    def _on_log_received(self, log_entry: dict[str, Any]) -> None:
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

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_import_fonts_click(self) -> None:
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
            if any(self._is_valid_drop(url) for url in urls):
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

        folders = [p for p in paths if p.is_dir()]
        fonts = [
            p for p in paths if p.is_file() and p.suffix.lower() in (".ttf", ".otf")
        ]

        import asyncio

        if folders:
            for folder in folders:
                asyncio.ensure_future(self._on_add_folder(folder))
        if fonts:
            asyncio.ensure_future(self._handle_font_drop(fonts))

        event.acceptProposedAction()

    def _is_valid_drop(self, url: Any) -> bool:
        """Helper to validate if a dropped URL is a directory or font file."""
        local_file = url.toLocalFile()
        if not local_file:
            return False
        p = Path(local_file)
        if p.is_dir():
            return True
        return p.suffix.lower() in (".ttf", ".otf")

    async def _handle_font_drop(self, files: list[Path]) -> None:
        """Handles font drop async."""
        if files:
            logger.info(f"Drag and drop: Ingesting files: {files}")
            await self.font_ingestion_service.ingest_files(files, source="drag_drop")
