from datetime import datetime, timezone
from typing import Any
import pytest
import asyncio
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from src.gui.main_window import MainWindow
from src.models.report import PipelineReport
from src.models.pipeline import (
    ShowSummary,
    ShowStatus,
    LibraryScanResult,
    LibraryScanOutput,
)


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class MockLogBridge(QObject):
    log_received = Signal(dict)

    def get_session_log(self) -> list:
        return []


class MockConfig:
    def __init__(self, path: Path) -> None:
        self.library_path = path
        self.dry_run = True

    def save_to_toml(self) -> None:
        pass


class MockIndexManager:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    async def load(self) -> list:
        return []

    async def save(self, shows: list) -> None:
        pass

    async def add_show(self, show: Any) -> None:
        pass

    async def update_status(self, path: Path, status: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_main_window_successful_run(mocker, tmp_path: Path) -> None:
    """Verify that a successful pipeline run locks the UI, updates progress, and populates results."""
    mock_runner = mocker.MagicMock()
    dummy_report = PipelineReport(
        run_timestamp=datetime.now(timezone.utc),
        duration_ms=1500.0,
        anime_title="Test Anime",
        episodes=[],
        total_fonts_found=0,
        genuine_misses=[],
    )
    mock_runner.run = mocker.AsyncMock(return_value=dummy_report)
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        return_value=LibraryScanOutput(episodes=[], font_directories=[], show_tree=())
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    window.run_button.setEnabled(True)

    # Execute underlying coroutine directly to bypass qasync scheduling in test environment
    await window._on_run_click.__wrapped__(window)

    # Assert PipelineRunner was called correctly
    mock_runner.run.assert_called_once()
    config_arg = mock_runner.run.call_args[0][0]
    assert config_arg.library_path == tmp_path

    # Assert UI re-enabled
    assert window.run_button.isEnabled() is True
    assert window._pipeline_running is False


@pytest.mark.asyncio
async def test_main_window_failed_run(mocker, tmp_path: Path) -> None:
    """Verify that a failed pipeline run catches exceptions, pops QMessageBox, and unlocks UI."""
    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(
        side_effect=RuntimeError("Muxing tool failed to execute")
    )
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        return_value=LibraryScanOutput(episodes=[], font_directories=[], show_tree=())
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    mock_dialog = mocker.patch("src.gui.widgets.error_dialog.show_error_dialog")

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    window.run_button.setEnabled(True)

    await window._on_run_click.__wrapped__(window)

    mock_runner.run.assert_called_once()
    mock_dialog.assert_called_once()

    # Assert UI re-enabled
    assert window.run_button.isEnabled() is True
    assert window._pipeline_running is False


@pytest.mark.asyncio
async def test_main_window_import_button_and_dialog_trigger(
    mocker, tmp_path: Path
) -> None:
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_ingestion.ingest_directories = mocker.AsyncMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    assert window.settings_btn is not None
    assert window.settings_btn.text() == "⚙ Settings"

    mocker.patch(
        "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
        return_value=str(tmp_path),
    )

    await window._on_import_fonts_click.__wrapped__(window)

    mock_ingestion.ingest_directories.assert_called_once_with(
        [Path(tmp_path)], source="manual_import"
    )


def test_main_window_drag_enter_event_valid(mocker, tmp_path: Path) -> None:
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    event = mocker.MagicMock()
    url = mocker.MagicMock()
    url.toLocalFile.return_value = "tests/fixtures/fonts/valid.ttf"
    event.mimeData().hasUrls.return_value = True
    event.mimeData().urls.return_value = [url]

    window.dragEnterEvent(event)

    event.acceptProposedAction.assert_called_once()
    assert "border: 3px solid" in window.styleSheet()


def test_main_window_drag_enter_event_invalid(mocker, tmp_path: Path) -> None:
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    event = mocker.MagicMock()
    url = mocker.MagicMock()
    url.toLocalFile.return_value = "some_notes.txt"
    event.mimeData().hasUrls.return_value = True
    event.mimeData().urls.return_value = [url]

    window.dragEnterEvent(event)

    event.ignore.assert_called_once()


@pytest.mark.asyncio
async def test_main_window_drop_event_dispatch(mocker, tmp_path: Path) -> None:
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_ingestion.ingest_files = mocker.AsyncMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    event = mocker.MagicMock()
    url = mocker.MagicMock()
    url.toLocalFile.return_value = "tests/fixtures/fonts/valid.ttf"
    event.mimeData().urls.return_value = [url]

    window.dropEvent(event)

    event.acceptProposedAction.assert_called_once()

    await asyncio.sleep(0.05)

    mock_ingestion.ingest_files.assert_called_once_with(
        [Path("tests/fixtures/fonts/valid.ttf")], source="drag_drop"
    )


def test_main_window_stop_button_hidden_initially(
    q_app, mocker, tmp_path: Path
) -> None:
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )
    assert window.stop_button.isVisible() is False


@pytest.mark.asyncio
async def test_main_window_add_show_folder(mocker, tmp_path: Path) -> None:
    mock_runner = mocker.MagicMock()
    mock_scan_output = LibraryScanOutput(episodes=[], font_directories=[], show_tree=())
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        return_value=mock_scan_output
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.load = mocker.AsyncMock(return_value=[])
    mock_index.add_show = mocker.AsyncMock()

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    show_path = tmp_path / "My Awesome Show"
    await window._on_add_folder.__wrapped__(window, show_path)

    mock_runner.library_scanner.scan_folder.assert_called_once_with(show_path)
    mock_index.add_show.assert_called_once()
    assert window._sidebar._list_widget.count() == 1


@pytest.mark.asyncio
async def test_main_window_show_selected(mocker, tmp_path: Path) -> None:
    mock_runner = mocker.MagicMock()
    episodes = [
        LibraryScanResult(episode_path=Path("ep1.mkv"), anime_title="My Show"),
    ]
    mock_scan_output = LibraryScanOutput(
        episodes=episodes, font_directories=[], show_tree=()
    )
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        return_value=mock_scan_output
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    await window._on_show_selected.__wrapped__(window, "My Show", tmp_path / "My Show")

    mock_runner.library_scanner.scan_folder.assert_called_once_with(
        tmp_path / "My Show"
    )
    mock_runner.library_scanner.scan.assert_not_called()
    assert window._episode_table._model.rowCount() == 1


# --- GAP 2: Explicit Refresh / FR-015 Tests ---


@pytest.mark.asyncio
async def test_main_window_startup_does_not_perform_full_scan(
    mocker, tmp_path: Path
) -> None:
    """FR-015: Verify app startup loads index without performing a full library scan."""
    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan = mocker.AsyncMock()

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.load = mocker.AsyncMock(
        return_value=[
            ShowSummary(
                "Show 1",
                tmp_path / "Show 1",
                ShowStatus.READY,
                12,
                0,
                "12 episodes found",
            )
        ]
    )

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    await window._on_startup.__wrapped__(window)

    mock_index.load.assert_called_once()
    mock_runner.library_scanner.scan.assert_not_called()
    assert window._sidebar._list_widget.count() == 1


@pytest.mark.asyncio
async def test_main_window_explicit_refresh_performs_single_full_scan(
    mocker, tmp_path: Path
) -> None:
    """FR-015: Explicit Refresh performs exactly one full library scan and updates index."""
    mock_runner = mocker.MagicMock()
    mock_scan_output = LibraryScanOutput(episodes=[], font_directories=[], show_tree=())
    mock_runner.library_scanner.scan = mocker.AsyncMock(return_value=mock_scan_output)

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.save = mocker.AsyncMock()

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    await window._on_refresh_index.__wrapped__(window)

    mock_runner.library_scanner.scan.assert_called_once_with(tmp_path)
    mock_index.save.assert_called_once()
    assert window._is_refreshing is False


@pytest.mark.asyncio
async def test_main_window_concurrent_refresh_prevented(mocker, tmp_path: Path) -> None:
    """FR-015: Duplicate/concurrent refresh trigger is safely ignored."""
    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan = mocker.AsyncMock()

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    window._is_refreshing = True
    await window._on_refresh_index.__wrapped__(window)

    mock_runner.library_scanner.scan.assert_not_called()


# --- GAP 3: FR-014 Functionality Regression Tests ---


def test_main_window_close_event_during_processing_prompts_user(
    mocker, tmp_path: Path
) -> None:
    """FR-014: closeEvent prompts for confirmation when pipeline is running."""
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )
    window._pipeline_running = True

    # User clicks 'No' (do not exit)
    mocker.patch(
        "PySide6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    )
    event_no = mocker.MagicMock()
    window.closeEvent(event_no)
    event_no.ignore.assert_called_once()

    # User clicks 'Yes' (confirm exit)
    mocker.patch(
        "PySide6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )
    event_yes = mocker.MagicMock()
    window.closeEvent(event_yes)
    event_yes.accept.assert_called_once()


def test_main_window_close_event_idle_accepts_immediately(
    mocker, tmp_path: Path
) -> None:
    """FR-014: closeEvent accepts immediately when pipeline is idle."""
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )
    window._pipeline_running = False

    event = mocker.MagicMock()
    window.closeEvent(event)
    event.accept.assert_called_once()


def test_main_window_stop_button_sets_stop_event(mocker, tmp_path: Path) -> None:
    """FR-014: Stop button sets asyncio.Event passed to pipeline runner."""
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    stop_ev = asyncio.Event()
    window._stop_event = stop_ev
    window.stop_button.setEnabled(True)

    window._on_stop_click()

    assert stop_ev.is_set() is True
    assert window.stop_button.isEnabled() is False


@pytest.mark.asyncio
async def test_main_window_undo_button_opens_dialog(mocker, tmp_path: Path) -> None:
    """FR-014: Undo button queries UndoService and opens UndoDialog."""
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    mock_undo = mocker.MagicMock()
    dummy_manifest = mocker.MagicMock()
    mock_undo.list_runs = mocker.AsyncMock(return_value=[dummy_manifest])

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
        undo_service=mock_undo,
    )

    mock_dialog_class = mocker.patch("src.gui.widgets.undo_dialog.UndoDialog")
    mock_dialog_inst = mocker.MagicMock()
    mock_dialog_class.return_value = mock_dialog_inst

    await window._on_undo_click.__wrapped__(window)

    mock_undo.list_runs.assert_called_once()
    mock_dialog_inst.populate.assert_called_once_with([dummy_manifest])
    mock_dialog_inst.exec.assert_called_once()


# --- STAGE A RECOVERY TESTS ---


def test_map_pipeline_report_preserves_full_path(tmp_path: Path) -> None:
    """Task 1: Verify map_pipeline_report preserves full ep.episode_path."""
    from src.gui.bootstrap import map_pipeline_report
    from src.models.report import (
        PipelineReport,
        EpisodeReport,
        EpisodeStatus as ModelStatus,
    )

    ep_path = tmp_path / "Season 1" / "ep01.mkv"
    dummy_report = PipelineReport(
        run_timestamp=datetime.now(timezone.utc),
        duration_ms=1000.0,
        anime_title="Test Anime",
        episodes=[
            EpisodeReport(
                episode_path=ep_path,
                status=ModelStatus.COMPLETE,
            )
        ],
        total_fonts_found=0,
        genuine_misses=[],
    )
    result = map_pipeline_report(dummy_report, tmp_path, dry_run=True)
    assert len(result.episodes) == 1
    assert result.episodes[0].name == "ep01.mkv"
    assert result.episodes[0].episode_path == ep_path


@pytest.mark.asyncio
async def test_main_window_mid_execution_ui_locking(mocker, tmp_path: Path) -> None:
    """Task 2: Real async test asserting UI control locking while pipeline execution is suspended."""
    entered_run_event = asyncio.Event()
    release_run_event = asyncio.Event()

    async def mock_run(*args, **kwargs):
        entered_run_event.set()
        await release_run_event.wait()
        return PipelineReport(
            run_timestamp=datetime.now(timezone.utc),
            duration_ms=100.0,
            anime_title="Test",
            episodes=[],
            total_fonts_found=0,
            genuine_misses=[],
        )

    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(side_effect=mock_run)
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        return_value=LibraryScanOutput(episodes=[], font_directories=[], show_tree=())
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )
    window.show()

    window.run_button.setEnabled(True)

    run_task = asyncio.create_task(window._on_run_click.__wrapped__(window))

    await entered_run_event.wait()

    assert window.run_button.isEnabled() is False
    assert window.stop_button.isVisible() is True
    assert window.stop_button.isEnabled() is True
    assert window.undo_button.isEnabled() is False
    assert window.settings_btn.isEnabled() is False
    assert window._pipeline_running is True
    assert isinstance(window._stop_event, asyncio.Event)

    release_run_event.set()
    await run_task

    assert window.run_button.isEnabled() is True
    assert window.stop_button.isVisible() is False
    assert window.undo_button.isEnabled() is True
    assert window.settings_btn.isEnabled() is True
    assert window._pipeline_running is False


@pytest.mark.asyncio
async def test_main_window_mid_execution_ui_locking_failure_cleanup(
    mocker, tmp_path: Path
) -> None:
    """Task 2: Assert UI controls are restored in finally block even on failure."""
    entered_run_event = asyncio.Event()
    release_run_event = asyncio.Event()

    async def mock_run_fail(*args, **kwargs):
        entered_run_event.set()
        await release_run_event.wait()
        raise RuntimeError("Fatal runner failure")

    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(side_effect=mock_run_fail)

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)
    mocker.patch("src.gui.widgets.error_dialog.show_error_dialog")

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )
    window.show()

    run_task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await entered_run_event.wait()

    assert window._pipeline_running is True

    release_run_event.set()
    await run_task

    assert window.run_button.isEnabled() is True
    assert window.stop_button.isVisible() is False
    assert window.undo_button.isEnabled() is True
    assert window.settings_btn.isEnabled() is True
    assert window._pipeline_running is False


@pytest.mark.asyncio
async def test_main_window_real_overlapping_refresh(mocker, tmp_path: Path) -> None:
    """Task 3: Real concurrency test for overlapping library refresh requests."""
    entered_scan_event = asyncio.Event()
    release_scan_event = asyncio.Event()

    async def mock_scan(*args, **kwargs):
        entered_scan_event.set()
        await release_scan_event.wait()
        return LibraryScanOutput(episodes=[], font_directories=[], show_tree=())

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan = mocker.AsyncMock(side_effect=mock_scan)

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.save = mocker.AsyncMock()

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    task1 = asyncio.create_task(window._on_refresh_index.__wrapped__(window))

    await entered_scan_event.wait()

    assert window._is_refreshing is True
    assert window._sidebar.is_refresh_enabled() is False

    await window._on_refresh_index.__wrapped__(window)

    assert mock_runner.library_scanner.scan.call_count == 1

    release_scan_event.set()
    await task1

    assert window._is_refreshing is False
    assert window._sidebar.is_refresh_enabled() is True
    assert mock_index.save.call_count == 1


@pytest.mark.asyncio
async def test_main_window_refresh_failure_resets_state(mocker, tmp_path: Path) -> None:
    """Task 3: Test cleanup on scan failure resets _is_refreshing and re-enables UI."""
    from src.errors import AnimeStudioError

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan = mocker.AsyncMock(
        side_effect=AnimeStudioError("Scanner failure")
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    await window._on_refresh_index.__wrapped__(window)

    assert window._is_refreshing is False
    assert window._sidebar.is_refresh_enabled() is True


def test_show_sidebar_refresh_button_encapsulation(mocker, q_app) -> None:
    """Task 4: Test set_refresh_enabled and is_refresh_enabled encapsulation on ShowSidebarWidget."""
    signal_bridge = mocker.MagicMock()
    from src.gui.widgets.show_sidebar import ShowSidebarWidget

    sidebar = ShowSidebarWidget(signal_bridge)

    assert sidebar.is_refresh_enabled() is True

    sidebar.set_refresh_enabled(False)
    assert sidebar.is_refresh_enabled() is False

    sidebar.set_refresh_enabled(True)
    assert sidebar.is_refresh_enabled() is True


@pytest.mark.asyncio
async def test_qt_signal_qasync_slot_bridge_smoke_test(mocker, tmp_path: Path) -> None:
    """Task 5: Real Qt signal -> qasync asyncSlot smoke test without calling .__wrapped__."""
    scan_called_event = asyncio.Event()

    async def mock_scan(path: Path) -> LibraryScanOutput:
        scan_called_event.set()
        return LibraryScanOutput(episodes=[], font_directories=[], show_tree=())

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan = mocker.AsyncMock(side_effect=mock_scan)

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = MockIndexManager(tmp_path)

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    # Emit real Qt signal via sidebar refresh button click
    window._sidebar._refresh_btn.click()

    # Wait for the qasync slot to execute and invoke scanner.scan
    await asyncio.wait_for(scan_called_event.wait(), timeout=2.0)

    # Verify that the async scanner was called without calling .__wrapped__
    mock_runner.library_scanner.scan.assert_called_once_with(tmp_path)
