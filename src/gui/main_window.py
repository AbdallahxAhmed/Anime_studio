from __future__ import annotations
import asyncio
import importlib
import logging
from datetime import datetime
from os.path import normcase
from typing import Any, TYPE_CHECKING
from pathlib import Path
from qasync import asyncSlot
from PySide6.QtGui import QFontMetrics, QKeyEvent, QResizeEvent

if TYPE_CHECKING:
    from src.models.run_manifest import RunManifest
from PySide6.QtCore import QTimer, Qt
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
    QSizePolicy,
)

from src.errors import AnimeStudioError, PipelineStoppedError
from src.gui.signals import SignalBridge
from src.gui.widgets import (
    ActivityFeedWidget,
    ProgressPanelWidget,
    ResultsTableWidget,
    ShowSidebarWidget,
    EpisodeTableWidget,
)
from src.gui.theme import TOKENS
from src.models.pipeline import LibraryScanOutput, ShowSummary, ShowStatus

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
        self._selection_generation = 0
        self._current_show_name: str | None = None
        self._current_show_path: Path | None = None
        self._stop_event: asyncio.Event | None = None
        self._show_name_text = "Select a show to start"

        # Initialize SignalBridge
        self.signal_bridge = SignalBridge()

        # Set window properties
        self.setWindowTitle("Anime Studio v3 - Forensics Dashboard")
        self.setAccessibleName("Anime Studio desktop application")
        self.setAccessibleDescription(
            "Anime subtitle forensics workspace with show navigation, episode "
            "selection, pipeline controls, progress, and activity log."
        )
        self.resize(1100, 800)
        self.setMinimumSize(800, 600)

        # Central Widget & Main Layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Root layout (vertical)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(
            TOKENS.spacing_16,
            TOKENS.spacing_16,
            TOKENS.spacing_16,
            TOKENS.spacing_16,
        )
        root_layout.setSpacing(TOKENS.spacing_12)

        # Header Bar (44px fixed height)
        self._header_bar = QWidget(central_widget)
        self._header_bar.setFixedHeight(TOKENS.header_height)
        header_layout = QHBoxLayout(self._header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(TOKENS.spacing_12)

        self.app_title_label = QLabel("Anime Studio", self._header_bar)
        self.app_title_label.setProperty("role", "app-title")
        self.app_title_label.setAccessibleName("Anime Studio")
        self.app_title_label.setAccessibleDescription("Application title")
        header_layout.addWidget(self.app_title_label)

        # Read-only library path label
        self._library_path_text = (
            str(self.config.library_path)
            if self.config.library_path
            else "No Library Path Configured"
        )
        self.library_path_label = QLabel(self._library_path_text, self._header_bar)
        self.library_path_label.setProperty("role", "muted")
        self.library_path_label.setAccessibleName("Library path")
        self.library_path_label.setAccessibleDescription(self._library_path_text)
        self.library_path_label.setToolTip(self._library_path_text)
        self.library_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.library_path_label.setWordWrap(False)
        self.library_path_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        header_layout.addWidget(self.library_path_label, 1)
        header_layout.addStretch()

        # This action imports local fonts; its label states the effect directly.
        self.settings_btn = QPushButton("Import Fonts", self._header_bar)
        self.settings_btn.setProperty("role", "secondary")
        self.settings_btn.setAccessibleName("Import fonts")
        self.settings_btn.setAccessibleDescription(
            "Choose a folder of local fonts to add to the font cache."
        )
        self.settings_btn.setToolTip("Import local fonts from a folder")
        header_layout.addWidget(self.settings_btn)

        root_layout.addWidget(self._header_bar)

        # Main splitter (horizontal)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, central_widget)
        root_layout.addWidget(self._splitter)

        # Left panel: ShowSidebarWidget
        self._sidebar = ShowSidebarWidget(self.signal_bridge, self._splitter)
        self._splitter.addWidget(self._sidebar)

        # Right panel: MainPanel (vertical)
        main_panel = QWidget(self._splitter)
        main_panel_layout = QVBoxLayout(main_panel)
        main_panel_layout.setContentsMargins(0, 0, 0, 0)
        main_panel_layout.setSpacing(TOKENS.spacing_12)

        # Show Header Bar (56px)
        self._show_header = QWidget(main_panel)
        self._show_header.setFixedHeight(TOKENS.header_height + TOKENS.spacing_12)
        show_header_layout = QHBoxLayout(self._show_header)
        show_header_layout.setContentsMargins(0, 0, 0, 0)
        show_header_layout.setSpacing(TOKENS.spacing_8)

        self._show_name_label = QLabel("Select a show to start", self._show_header)
        self._show_name_label.setProperty("role", "show-title")
        self._show_name_label.setAccessibleName("Selected show")
        self._show_name_label.setAccessibleDescription("No show selected")
        show_header_layout.addWidget(self._show_name_label, 1)

        self._show_subtitle_label = QLabel("", self._show_header)
        self._show_subtitle_label.setProperty("role", "secondary")
        self._show_subtitle_label.setAccessibleName("Selected show episode count")
        show_header_layout.addWidget(self._show_subtitle_label)

        self.undo_button = QPushButton("Undo", self._show_header)
        self.undo_button.setMinimumWidth(76)
        self.undo_button.setProperty("role", "secondary")
        self.undo_button.setAccessibleName("Undo a previous pipeline run")
        self.undo_button.setAccessibleDescription(
            "Open the run history and undo a selected prior pipeline operation."
        )
        self.undo_button.setToolTip("Undo a previous pipeline run")
        show_header_layout.addWidget(self.undo_button)

        self.stop_button = QPushButton("Stop", self._show_header)
        self.stop_button.setMinimumWidth(116)
        self.stop_button.setProperty("role", "danger")
        self.stop_button.setAccessibleName("Stop pipeline")
        self.stop_button.setAccessibleDescription(
            "Request a safe, cooperative stop for the active pipeline run."
        )
        self.stop_button.setToolTip("Stop the active pipeline run")
        self.stop_button.setVisible(False)
        show_header_layout.addWidget(self.stop_button)

        self.run_button = QPushButton("Run 0 selected", self._show_header)
        self.run_button.setMinimumWidth(148)
        self.run_button.setProperty("role", "primary")
        self.run_button.setAccessibleName("Run 0 selected episodes")
        self.run_button.setAccessibleDescription(
            "Select episodes first, then run the subtitle forensics pipeline."
        )
        self.run_button.setToolTip("Run the selected episodes")
        self.run_button.setEnabled(False)
        show_header_layout.addWidget(self.run_button)

        main_panel_layout.addWidget(self._show_header)

        # Episode Table Widget
        self._episode_table = EpisodeTableWidget(main_panel)
        main_panel_layout.addWidget(self._episode_table)

        self.empty_state_label = QLabel(
            "Select a show to review its subtitle-ready episodes.", main_panel
        )
        self.empty_state_label.setProperty("role", "secondary")
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setAccessibleName("Episode workspace status")
        self.empty_state_label.setAccessibleDescription(self.empty_state_label.text())
        main_panel_layout.addWidget(self.empty_state_label)
        self._episode_table.setVisible(False)

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

        self._splitter.addWidget(main_panel)

        # Set initial splitter sizes (220px fixed for sidebar, rest for main panel)
        self._splitter.setSizes([TOKENS.sidebar_width, 880])

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

        QWidget.setTabOrder(self.settings_btn, self._sidebar._list_widget)
        QWidget.setTabOrder(self._sidebar._list_widget, self._episode_table._table)
        QWidget.setTabOrder(self._episode_table._table, self.undo_button)
        QWidget.setTabOrder(self.undo_button, self.run_button)
        QWidget.setTabOrder(self.run_button, self.stop_button)
        QWidget.setTabOrder(self.stop_button, self.activity_feed.toggle_button)

        # Setup Drag & Drop
        self.setAcceptDrops(True)
        self._default_style = self.styleSheet()
        self._render_library_path_label()

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

        self._invalidate_active_show()
        self._is_refreshing = True
        self._sidebar.set_navigation_enabled(False)
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
            if not self._pipeline_running:
                self._sidebar.set_navigation_enabled(True)

    def _invalidate_active_show(self) -> int:
        """Clear the active show and return its new selection generation."""
        self._selection_generation += 1
        self._current_show_name = None
        self._current_show_path = None
        self._show_name_text = "Select a show to start"
        self._show_name_label.setText(self._show_name_text)
        self._show_name_label.setToolTip("")
        self._show_name_label.setAccessibleDescription("No show selected")
        self._render_show_name_label()
        self._show_name_label.setAccessibleDescription("No show selected")
        self._show_subtitle_label.setText("")
        self._episode_table.populate([])
        self._episode_table.setVisible(False)
        self.empty_state_label.setText(
            "Select a show to review its subtitle-ready episodes."
        )
        self.empty_state_label.setAccessibleDescription(self.empty_state_label.text())
        self.empty_state_label.setVisible(True)
        self.run_button.setText("Run 0 selected")
        self.run_button.setAccessibleName("Run 0 selected episodes")
        self.run_button.setToolTip("Select one or more episodes to run")
        self.run_button.setEnabled(False)
        return self._selection_generation

    def _is_library_root(self, folder_path: Path) -> bool:
        """Return whether a selected folder resolves to the configured library root."""
        library_path = getattr(self.config, "library_path", None)
        if not library_path:
            return False

        configured_root = Path(library_path).expanduser().resolve()
        selected_root = folder_path.expanduser().resolve()
        return normcase(str(configured_root)) == normcase(str(selected_root))

    def _display_scan_result(
        self, name: str, path: Path, scan_output: LibraryScanOutput
    ) -> None:
        """Display an already-computed folder scan without performing I/O."""
        self._current_show_name = name
        self._current_show_path = path
        self._show_name_text = name
        self._show_name_label.setText(name)
        self._show_name_label.setToolTip(name)
        self._show_name_label.setAccessibleDescription(f"Selected show: {name}")
        self._episode_table.populate(scan_output.episodes)
        subtitle = f"{len(scan_output.episodes)} episodes found"
        self._show_subtitle_label.setText(f" ({subtitle})")
        self._show_subtitle_label.setToolTip(subtitle)
        self._show_subtitle_label.setAccessibleDescription(subtitle)
        has_episodes = bool(scan_output.episodes)
        self._episode_table.setVisible(has_episodes)
        self.empty_state_label.setVisible(not has_episodes)
        if not has_episodes:
            self.empty_state_label.setText(
                "No subtitle-ready episodes were found for this show."
            )
            self.empty_state_label.setAccessibleDescription(
                self.empty_state_label.text()
            )
        self.progress_panel.setVisible(False)
        self._render_show_name_label()
        QTimer.singleShot(0, self._render_show_name_label)

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_show_selected(self, name: str, path: Path) -> None:
        """Load episodes for selected show into EpisodeTableWidget."""
        request_generation = self._invalidate_active_show()
        requested_name = name
        requested_path = Path(path).expanduser().resolve()

        self.progress_panel.set_status("Scanning folder...")
        self.progress_panel.setVisible(True)
        self.progress_panel.progress_bar.setRange(0, 0)

        try:
            scan_output = await self.pipeline_runner.library_scanner.scan_folder(
                requested_path
            )
            if request_generation != self._selection_generation:
                return
            self._display_scan_result(requested_name, requested_path, scan_output)
        except (AnimeStudioError, OSError) as e:
            if request_generation != self._selection_generation:
                return
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

        if self._is_library_root(path):
            logger.info(
                "User selected library root in Add Folder; ignoring single-show scan"
            )
            QMessageBox.information(
                self,
                "Library Root Selected",
                "This is the configured library root. Use Refresh to rebuild the "
                "complete library index, or select one individual show folder.",
            )
            return

        request_generation = self._invalidate_active_show()
        self.progress_panel.set_status(f"Adding show: {path.name}...")
        self.progress_panel.setVisible(True)
        self.progress_panel.progress_bar.setRange(0, 0)

        try:
            resolved = path.expanduser().resolve()
            scan_output = await self.pipeline_runner.library_scanner.scan_folder(
                resolved
            )
            status = (
                ShowStatus.READY if scan_output.episodes else ShowStatus.NO_SUBTITLE
            )
            summary = ShowSummary(
                name=resolved.name,
                path=resolved,
                status=status,
                episode_count=len(scan_output.episodes),
                processed_count=0,
                subtitle_text=f"{len(scan_output.episodes)} episodes found",
            )
            self._sidebar.add_show(summary)
            await self._show_index.add_show(summary)
            if request_generation != self._selection_generation:
                return
            self._display_scan_result(summary.name, resolved, scan_output)
        except (AnimeStudioError, OSError) as e:
            if request_generation != self._selection_generation:
                return
            logger.error(f"Failed to add folder: {e}")
            self.progress_panel.set_error()
            self.progress_panel.set_status(f"Failed to add folder: {e}")

    def _on_selection_changed(self, paths: list[Path]) -> None:
        count = len(paths)
        self.run_button.setText(f"Run {count} selected")
        self.run_button.setAccessibleName(f"Run {count} selected episodes")
        self.run_button.setAccessibleDescription(
            f"Run the subtitle forensics pipeline for exactly {count} selected "
            "episode(s)."
        )
        self.run_button.setToolTip(f"Run {count} selected episode(s)")
        self.run_button.setEnabled(
            count > 0
            and self._current_show_path is not None
            and self._current_show_name is not None
            and not self._pipeline_running
        )

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_run_click(self) -> None:
        """Trigger the forensics pipeline runner asynchronously without blocking the UI thread."""
        library_path = self.config.library_path
        if not library_path:
            QMessageBox.warning(
                self,
                "No Library Selected",
                "Please select an anime library directory first.",
            )
            return

        run_generation = self._selection_generation
        run_show_path = self._current_show_path
        run_show_name = self._current_show_name
        run_selected_paths = frozenset(
            path.expanduser().resolve()
            for path in self._episode_table.get_selected_paths()
        )

        if self._pipeline_running:
            return

        if run_show_path is None or run_show_name is None:
            QMessageBox.warning(
                self,
                "No Show Selected",
                "Please select a show before running selected episodes.",
            )
            return

        if not run_selected_paths:
            QMessageBox.warning(
                self,
                "No Episodes Selected",
                "Please select at least one episode before running.",
            )
            return

        pre_run_status = self._sidebar.get_show_status(run_show_path)
        if pre_run_status is None:
            pre_run_status = ShowStatus.READY

        p = Path(library_path).expanduser().resolve()
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
        self._episode_table.setEnabled(False)
        self._sidebar.set_navigation_enabled(False)
        self.stop_button.setVisible(True)
        self.stop_button.setEnabled(True)
        self.stop_button.setText("Stop")
        self.stop_button.setAccessibleName("Stop pipeline")
        self.stop_button.setAccessibleDescription(
            "Request a safe, cooperative stop for the active pipeline run."
        )
        self.stop_button.setToolTip("Stop the active pipeline run")
        self.results_table.clear_results()
        self.results_table.setVisible(False)

        stop_event = asyncio.Event()
        self._stop_event = stop_event
        processing_status_persisted = False

        try:
            # The first await after locking the UI must remain inside this
            # guarded lifecycle so every expected failure reaches cleanup.
            await self._show_index.update_status(run_show_path, ShowStatus.PROCESSING)
            processing_status_persisted = True
            if stop_event.is_set():
                raise PipelineStoppedError("Pipeline stopped by user")
            if (
                run_generation == self._selection_generation
                and run_show_path == self._current_show_path
                and run_show_name == self._current_show_name
            ):
                self._sidebar.update_show_status(run_show_path, ShowStatus.PROCESSING)

            self.signal_bridge.progress_updated.emit(
                ProgressState(
                    stage=ProgressStage.SCANNING,
                    status_text="Executing pipeline...",
                )
            )

            config = PipelineConfig(
                library_path=p,
                discovery_root=run_show_path,
                dry_run=self.config.dry_run
                if hasattr(self.config, "dry_run")
                else False,
                sync_enabled=True,
                anime_title=run_show_name,
                selected_paths=run_selected_paths,
            )

            report = await self.pipeline_runner.run(
                config,
                stop_event=stop_event,
                checkpoint_manager=self._checkpoint_manager,
                undo_service=self._undo_service,
            )

            # A runner can complete an in-flight bounded operation after Stop.
            # Never render a successful result once the UI has observed Stop.
            if stop_event.is_set():
                raise PipelineStoppedError("Pipeline stopped by user")

            run_result = map_pipeline_report(report, p, config.dry_run)

            # Update statuses on completion
            final_status = ShowStatus.ALL_DONE
            is_current_run_show = (
                run_generation == self._selection_generation
                and run_show_path == self._current_show_path
                and run_show_name == self._current_show_name
            )
            if is_current_run_show:
                self.signal_bridge.pipeline_finished.emit(run_result)
            for ep_res in run_result.episodes:
                status_str = (
                    ep_res.status.value
                    if hasattr(ep_res.status, "value")
                    else str(ep_res.status)
                )
                if is_current_run_show:
                    self._episode_table.update_episode_status(
                        ep_res.episode_path, status_str
                    )
                if status_str.lower() in ("failed", "error"):
                    final_status = ShowStatus.WARNING

            if stop_event.is_set():
                raise PipelineStoppedError("Pipeline stopped by user")
            if is_current_run_show:
                self._sidebar.update_show_status(run_show_path, final_status)
            await self._show_index.update_status(run_show_path, final_status)
            if stop_event.is_set():
                raise PipelineStoppedError("Pipeline stopped by user")
            self.signal_bridge.progress_updated.emit(
                ProgressState(
                    stage=ProgressStage.COMPLETE,
                    status_text="Pipeline executed successfully!",
                )
            )

        except asyncio.CancelledError:
            raise
        except PipelineStoppedError:
            is_current_run_show = (
                run_generation == self._selection_generation
                and run_show_path == self._current_show_path
                and run_show_name == self._current_show_name
            )
            if is_current_run_show:
                self._sidebar.update_show_status(run_show_path, pre_run_status)
                self.progress_panel.setVisible(True)
                self.signal_bridge.progress_updated.emit(
                    ProgressState(
                        stage=ProgressStage.STOPPED,
                        status_text="Pipeline stopped by user.",
                    )
                )
            if processing_status_persisted:
                try:
                    await self._show_index.update_status(run_show_path, pre_run_status)
                except Exception as restore_error:
                    # Do not let a secondary persistent-status failure escape
                    # a qasync slot or recursively attempt another write.
                    logger.warning(
                        "Could not restore show status after user stop: %s",
                        restore_error,
                    )
            self.signal_bridge.log_received.emit(
                {
                    "event": "Pipeline stopped by user.",
                    "level": "info",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except (AnimeStudioError, OSError, ValueError, RuntimeError) as e:
            logger.error(f"Forensics pipeline execution failed: {e}")
            self.signal_bridge.progress_updated.emit(
                ProgressState(
                    stage=ProgressStage.ERROR, status_text=f"Pipeline failed: {e}"
                )
            )
            self.signal_bridge.pipeline_error.emit(str(e))

            if processing_status_persisted:
                if (
                    run_generation == self._selection_generation
                    and run_show_path == self._current_show_path
                    and run_show_name == self._current_show_name
                ):
                    self._sidebar.update_show_status(run_show_path, ShowStatus.WARNING)
                await self._show_index.update_status(run_show_path, ShowStatus.WARNING)

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
            self.undo_button.setEnabled(True)
            self.settings_btn.setEnabled(True)
            self._episode_table.setEnabled(True)
            self._sidebar.set_navigation_enabled(not self._is_refreshing)
            self._on_selection_changed(self._episode_table.get_selected_paths())

    def _on_stop_click(self) -> None:
        """Handle Stop button click by setting the stop event."""
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Stopping...")
            self.stop_button.setAccessibleName("Stopping pipeline")
            self.stop_button.setAccessibleDescription(
                "A safe stop has been requested. Running operations will finish "
                "before the interface returns to idle."
            )
            self.stop_button.setToolTip("Stopping the active pipeline run")

    @asyncSlot()  # type: ignore[untyped-decorator]  # qasync.asyncSlot decorator lacks type hints
    async def _on_undo_click(self) -> None:
        """Open the Undo dialog and run the selected undo action."""
        if not self._undo_service:
            return
        library_path = self.config.library_path or (
            self._current_show_path.parent
            if self._current_show_path is not None
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

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep a narrow header readable while retaining the full path in a tooltip."""
        super().resizeEvent(event)
        self._render_library_path_label()
        self._render_show_name_label()
        QTimer.singleShot(0, self._render_library_path_label)
        QTimer.singleShot(0, self._render_show_name_label)

    def _render_library_path_label(self) -> None:
        """Elide a long library path visually without changing its identity."""
        available_width = self.library_path_label.width()
        if available_width <= 0:
            self.library_path_label.setText(self._library_path_text)
            return
        rendered = QFontMetrics(self.library_path_label.font()).elidedText(
            self._library_path_text,
            Qt.TextElideMode.ElideMiddle,
            available_width,
        )
        self.library_path_label.setText(rendered)
        self.library_path_label.setToolTip(self._library_path_text)
        self.library_path_label.setAccessibleDescription(self._library_path_text)

    def _render_show_name_label(self) -> None:
        """Elide long show titles in the header while retaining the full tooltip."""
        available_width = self._show_name_label.width()
        if available_width <= 0:
            self._show_name_label.setText(self._show_name_text)
            return
        self._show_name_label.setText(
            QFontMetrics(self._show_name_label.font()).elidedText(
                self._show_name_text,
                Qt.TextElideMode.ElideRight,
                available_width,
            )
        )
        self._show_name_label.setToolTip(self._show_name_text)
        self._show_name_label.setAccessibleDescription(
            f"Selected show: {self._show_name_text}"
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Use Escape as a safe Stop shortcut only while a pipeline is active."""
        if event.key() == Qt.Key.Key_Escape and self._pipeline_running:
            self._on_stop_click()
            event.accept()
            return
        super().keyPressEvent(event)

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
                self.setStyleSheet(
                    f"QMainWindow {{ border: 2px solid {TOKENS.accent}; }}"
                )
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
