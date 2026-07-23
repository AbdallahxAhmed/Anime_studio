from datetime import datetime, timezone
import logging
from typing import Any
import pytest
import asyncio
from pathlib import Path
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.errors import PipelineStoppedError
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

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[dict[str, object]] = []

    def record(self, entry: dict[str, object]) -> None:
        entry_copy = entry.copy()
        self.entries.append(entry_copy)
        self.log_received.emit(entry_copy)

    def get_session_log(self) -> list:
        return list(self.entries)


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


def _set_active_show(window: MainWindow, path: Path, name: str = "Test Show") -> Path:
    episode_path = path / "episode_01.mkv"
    window._display_scan_result(
        name,
        path,
        LibraryScanOutput(
            episodes=[LibraryScanResult(episode_path=episode_path, anime_title=name)],
            font_directories=[],
            show_tree=(),
        ),
    )
    return episode_path


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
    show_path = tmp_path / "Ranma"
    episode_path = _set_active_show(window, show_path, "Ranma Display Name")

    # Execute underlying coroutine directly to bypass qasync scheduling in test environment
    await window._on_run_click.__wrapped__(window)

    # Assert PipelineRunner was called correctly
    mock_runner.run.assert_called_once()
    config_arg = mock_runner.run.call_args[0][0]
    assert config_arg.library_path == tmp_path
    assert config_arg.discovery_root == show_path.resolve()
    assert config_arg.anime_title == "Ranma Display Name"
    assert config_arg.selected_paths == frozenset({episode_path.resolve()})

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
    _set_active_show(window, tmp_path / "Ranma", "Ranma Display Name")

    await window._on_run_click.__wrapped__(window)

    mock_runner.run.assert_called_once()
    mock_dialog.assert_called_once()

    # Assert UI re-enabled
    assert window.run_button.isEnabled() is True
    assert window._pipeline_running is False


@pytest.mark.asyncio
async def test_main_window_run_selected_requires_active_show(
    mocker, tmp_path: Path
) -> None:
    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock()
    warning = mocker.patch.object(QMessageBox, "warning")
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )

    await window._on_run_click.__wrapped__(window)

    mock_runner.run.assert_not_called()
    warning.assert_called_once_with(
        window,
        "No Show Selected",
        "Please select a show before running selected episodes.",
    )


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
    assert window.settings_btn.text() == "Import Fonts"
    assert window.settings_btn.toolTip() == "Import local fonts from a folder"
    assert window.settings_btn.accessibleName() == "Import fonts"

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
    assert "border: 2px solid #3B82F6" in window.styleSheet()


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
    ingestion_started = asyncio.Event()

    async def ingest_files(files: list[Path], *, source: str) -> None:
        assert files == [Path("tests/fixtures/fonts/valid.ttf")]
        assert source == "drag_drop"
        ingestion_started.set()

    mock_ingestion.ingest_files = mocker.AsyncMock(side_effect=ingest_files)
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
    await ingestion_started.wait()

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

    assert mock_runner.library_scanner.scan_folder.call_count == 1
    mock_index.add_show.assert_called_once()
    assert window._sidebar._list_widget.count() == 1


@pytest.mark.asyncio
async def test_main_window_add_show_folder_single_scan_and_sync(
    mocker, tmp_path: Path
) -> None:
    """Verify Add Folder invokes scan_folder() exactly once while populating sidebar, displaying episodes, and synchronizing Run button."""
    show_path = tmp_path / "Ranma"
    episodes = [
        LibraryScanResult(episode_path=show_path / "ep1.mkv", anime_title="Ranma"),
        LibraryScanResult(episode_path=show_path / "ep2.mkv", anime_title="Ranma"),
    ]
    mock_scan_output = LibraryScanOutput(
        episodes=episodes, font_directories=[], show_tree=()
    )

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        return_value=mock_scan_output
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.add_show = mocker.AsyncMock()

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    await window._on_add_folder.__wrapped__(window, show_path)

    # Invokes scan_folder() EXACTLY ONCE
    assert mock_runner.library_scanner.scan_folder.call_count == 1
    mock_runner.library_scanner.scan_folder.assert_called_once()
    assert mock_runner.library_scanner.scan_folder.call_args.args[0] == show_path

    # Adds ShowSummary to index
    mock_index.add_show.assert_called_once()

    # Populates sidebar
    assert window._sidebar._list_widget.count() == 1

    # Displays discovered episodes in EpisodeTableWidget immediately
    assert window._episode_table._model.rowCount() == 2
    assert window._episode_table.get_selected_paths() == [
        show_path / "ep1.mkv",
        show_path / "ep2.mkv",
    ]
    assert all(
        window._episode_table._model.data(
            window._episode_table._model.index(row, 0),
            Qt.ItemDataRole.CheckStateRole,
        )
        == Qt.CheckState.Checked
        for row in range(2)
    )

    # Synchronizes Run button count and enabled state
    assert window.run_button.text() == "Run 2 selected"
    assert window.run_button.isEnabled() is True
    assert not hasattr(window, "_pending_scan_output")

    # An explicit later sidebar selection intentionally performs a fresh scan.
    await window._on_show_selected.__wrapped__(window, "Ranma", show_path)
    assert mock_runner.library_scanner.scan_folder.call_count == 2


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

    mock_runner.library_scanner.scan_folder.assert_called_once()
    assert mock_runner.library_scanner.scan_folder.call_args.args[0] == (
        tmp_path / "My Show"
    )
    mock_runner.library_scanner.scan.assert_not_called()
    assert window._episode_table._model.rowCount() == 1


@pytest.mark.asyncio
async def test_main_window_run_button_tracks_episode_model_selection(
    mocker, tmp_path: Path
) -> None:
    """The Run button always reflects the episode model's selected paths."""
    show_path = tmp_path / "Selection Show"
    episodes = [
        LibraryScanResult(episode_path=show_path / "01.mkv", anime_title="Selection"),
        LibraryScanResult(episode_path=show_path / "02.mkv", anime_title="Selection"),
        LibraryScanResult(episode_path=show_path / "03.mkv", anime_title="Selection"),
    ]
    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        return_value=LibraryScanOutput(
            episodes=episodes, font_directories=[], show_tree=()
        )
    )
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )

    await window._on_show_selected.__wrapped__(window, "Selection", show_path)
    assert window._episode_table.get_selected_paths() == [
        show_path / "01.mkv",
        show_path / "02.mkv",
        show_path / "03.mkv",
    ]
    assert window.run_button.text() == "Run 3 selected"
    assert window.run_button.isEnabled() is True

    window._episode_table.set_all_checked(False)
    assert window._episode_table.get_selected_paths() == []
    assert window.run_button.text() == "Run 0 selected"
    assert window.run_button.isEnabled() is False

    for row, expected_count in ((0, 1), (1, 2)):
        window._episode_table._model.setData(
            window._episode_table._model.index(row, 0),
            Qt.CheckState.Checked,
            Qt.ItemDataRole.CheckStateRole,
        )
        assert len(window._episode_table.get_selected_paths()) == expected_count
        assert window.run_button.text() == f"Run {expected_count} selected"
        assert window.run_button.isEnabled() is True

    window._episode_table.set_all_checked(True)
    assert len(window._episode_table.get_selected_paths()) == 3
    assert window.run_button.text() == "Run 3 selected"

    window._episode_table.populate(
        [
            LibraryScanResult(
                episode_path=tmp_path / "Other Show" / "01.mkv",
                anime_title="Other",
            )
        ]
    )
    assert window._episode_table.get_selected_paths() == [
        tmp_path / "Other Show" / "01.mkv"
    ]
    assert window.run_button.text() == "Run 1 selected"
    assert window.run_button.isEnabled() is True


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

    mock_runner.library_scanner.scan.assert_called_once()
    assert mock_runner.library_scanner.scan.call_args.args[0] == tmp_path
    mock_index.save.assert_called_once()
    assert window._is_refreshing is False


@pytest.mark.asyncio
async def test_main_window_concurrent_refresh_prevented(mocker, tmp_path: Path) -> None:
    """The legacy flag cannot bypass the authoritative active-scan lifecycle."""
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

    mock_runner.library_scanner.scan.assert_called_once()


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


def test_main_window_keyboard_and_accessibility_surface(
    qtbot, mocker, tmp_path: Path
) -> None:
    """Primary controls remain textual, discoverable, and keyboard reachable."""
    long_library_path = tmp_path / (("Long Library العربية 日本語 " * 12).strip())
    window = MainWindow(
        pipeline_runner=mocker.MagicMock(),
        log_bridge=MockLogBridge(),
        config=MockConfig(long_library_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )
    qtbot.addWidget(window)
    window.resize(800, 600)
    window.show()

    assert window.accessibleName() == "Anime Studio desktop application"
    assert window.settings_btn.text() == "Import Fonts"
    assert window.settings_btn.accessibleName() == "Import fonts"
    assert window.run_button.accessibleName() == "Run 0 selected episodes"
    assert window.stop_button.accessibleName() == "Stop pipeline"
    assert window.empty_state_label.isVisible()
    assert window.library_path_label.toolTip() == str(long_library_path)
    assert window.library_path_label.accessibleDescription() == str(long_library_path)

    focus_chain = []
    current = window.settings_btn
    for _ in range(20):
        current = current.nextInFocusChain()
        focus_chain.append(current)
    assert window._sidebar._list_widget in focus_chain
    assert focus_chain.index(window._sidebar._list_widget) < focus_chain.index(
        window.undo_button
    )


def test_main_window_escape_requests_cooperative_stop(
    qtbot, mocker, tmp_path: Path
) -> None:
    """Escape requests the same neutral Stop flow rather than a forced close."""
    window = MainWindow(
        pipeline_runner=mocker.MagicMock(),
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )
    qtbot.addWidget(window)
    window.show()
    window._pipeline_running = True
    window._stop_event = asyncio.Event()
    window.stop_button.setVisible(True)

    qtbot.keyClick(window, Qt.Key.Key_Escape)

    assert window._stop_event.is_set()
    assert window.stop_button.text() == "Stopping..."
    assert window.stop_button.accessibleName() == "Stopping pipeline"


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
    _set_active_show(window, tmp_path / "Test Show")

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
    _set_active_show(window, tmp_path / "Test Show")

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
async def test_main_window_stop_is_neutral_and_restores_pre_run_status(
    mocker, tmp_path: Path
) -> None:
    """User Stop is neither a successful run nor a pipeline failure."""
    from src.errors import PipelineStoppedError

    started = asyncio.Event()
    status_updates: list[tuple[Path, ShowStatus]] = []

    async def stopped_run(*_args: object, **kwargs: object) -> PipelineReport:
        stop_event = kwargs["stop_event"]
        assert isinstance(stop_event, asyncio.Event)
        started.set()
        await stop_event.wait()
        raise PipelineStoppedError("Pipeline stopped by user")

    async def update_status(path: Path, status: ShowStatus) -> None:
        status_updates.append((path, status))

    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(side_effect=stopped_run)
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.update_status = mocker.AsyncMock(side_effect=update_status)
    error_dialog = mocker.patch("src.gui.widgets.error_dialog.show_error_dialog")
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )
    show_path = tmp_path / "Stopped Show"
    _set_active_show(window, show_path, "Stopped Show")
    window._sidebar.add_show(
        ShowSummary(
            name="Stopped Show",
            path=show_path.resolve(),
            status=ShowStatus.READY,
            episode_count=1,
            processed_count=0,
            subtitle_text="1 episode found",
        )
    )

    run_task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await started.wait()
    window._on_stop_click()
    window._on_stop_click()
    await run_task

    assert error_dialog.call_count == 0
    assert window.results_table.isVisible() is False
    assert window.progress_panel.status_label.text() == "Pipeline stopped by user."
    assert window.run_button.isEnabled() is True
    assert window.stop_button.isVisible() is False
    assert window._pipeline_running is False
    assert status_updates == [
        (show_path.resolve(), ShowStatus.PROCESSING),
        (show_path.resolve(), ShowStatus.READY),
    ]
    assert window._sidebar.get_show_status(show_path.resolve()) is ShowStatus.READY


@pytest.mark.asyncio
async def test_main_window_stop_restoration_failure_is_bounded_and_neutral(
    mocker, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed status restore cannot escape the slot or become a run failure."""
    started = asyncio.Event()
    status_updates: list[tuple[Path, ShowStatus]] = []

    async def stopped_run(*_args: object, **kwargs: object) -> PipelineReport:
        stop_event = kwargs["stop_event"]
        assert isinstance(stop_event, asyncio.Event)
        started.set()
        await stop_event.wait()
        raise PipelineStoppedError("Pipeline stopped by user")

    async def update_status(path: Path, status: ShowStatus) -> None:
        status_updates.append((path, status))
        if status is ShowStatus.READY:
            raise OSError("index is unavailable")

    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(side_effect=stopped_run)
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.update_status = mocker.AsyncMock(side_effect=update_status)
    error_dialog = mocker.patch("src.gui.widgets.error_dialog.show_error_dialog")
    log_bridge = MockLogBridge()
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )
    show_path = tmp_path / "Stopped Show"
    _set_active_show(window, show_path, "Stopped Show")
    window._sidebar.add_show(
        ShowSummary(
            name="Stopped Show",
            path=show_path.resolve(),
            status=ShowStatus.READY,
            episode_count=1,
            processed_count=0,
            subtitle_text="1 episode found",
        )
    )
    caplog.set_level(logging.WARNING, logger="anime_studio.gui.main_window")

    run_task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await started.wait()
    window._on_stop_click()
    await run_task

    assert error_dialog.call_count == 0
    assert window.progress_panel.status_label.text() == "Pipeline stopped by user."
    assert window.run_button.isEnabled()
    assert status_updates == [
        (show_path.resolve(), ShowStatus.PROCESSING),
        (show_path.resolve(), ShowStatus.READY),
    ]
    restore_warnings = [
        record
        for record in caplog.records
        if "Could not restore show status after user stop" in record.getMessage()
    ]
    assert len(restore_warnings) == 1
    assert [entry["event"] for entry in log_bridge.get_session_log()] == [
        "Pipeline stop requested",
        "Pipeline stopped by user",
    ]


@pytest.mark.asyncio
async def test_main_window_treats_late_success_after_stop_as_neutral(
    mocker, tmp_path: Path
) -> None:
    """A bounded runner operation finishing after Stop cannot render success."""
    started = asyncio.Event()
    status_updates: list[tuple[Path, ShowStatus]] = []
    stopped_events: list[dict[str, object]] = []

    async def late_success(*_args: object, **kwargs: object) -> PipelineReport:
        stop_event = kwargs["stop_event"]
        assert isinstance(stop_event, asyncio.Event)
        started.set()
        await stop_event.wait()
        return PipelineReport(
            run_timestamp=datetime.now(timezone.utc),
            duration_ms=1.0,
            anime_title="Stopped Show",
            episodes=[],
            total_fonts_found=0,
            genuine_misses=[],
        )

    async def update_status(path: Path, status: ShowStatus) -> None:
        status_updates.append((path, status))

    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(side_effect=late_success)
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.update_status = mocker.AsyncMock(side_effect=update_status)
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )
    show_path = tmp_path / "Stopped Show"
    _set_active_show(window, show_path, "Stopped Show")
    window._sidebar.add_show(
        ShowSummary(
            name="Stopped Show",
            path=show_path.resolve(),
            status=ShowStatus.READY,
            episode_count=1,
            processed_count=0,
            subtitle_text="1 episode found",
        )
    )
    window.signal_bridge.log_received.connect(stopped_events.append)

    run_task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await started.wait()
    window._on_stop_click()
    await run_task

    assert window.results_table.isVisible() is False
    assert window.progress_panel.status_label.text() == "Pipeline stopped by user."
    assert status_updates == [
        (show_path.resolve(), ShowStatus.PROCESSING),
        (show_path.resolve(), ShowStatus.READY),
    ]
    assert [event["event"] for event in stopped_events] == [
        "Pipeline stop requested",
        "Pipeline stopped by user",
    ]


@pytest.mark.asyncio
async def test_main_window_stop_events_persist_across_a_deliberate_second_run(
    mocker, tmp_path: Path
) -> None:
    """A stopped run stays exportable after the user starts a later successful run."""
    first_run_started = asyncio.Event()
    calls = 0

    async def run_pipeline(*_args: object, **kwargs: object) -> PipelineReport:
        nonlocal calls
        calls += 1
        if calls == 1:
            stop_event = kwargs["stop_event"]
            assert isinstance(stop_event, asyncio.Event)
            first_run_started.set()
            await stop_event.wait()
        return PipelineReport(
            run_timestamp=datetime.now(timezone.utc),
            duration_ms=1.0,
            anime_title="Stopped Show",
            episodes=[],
            total_fonts_found=0,
            genuine_misses=[],
        )

    log_bridge = MockLogBridge()
    runner = mocker.MagicMock()
    runner.run = mocker.AsyncMock(side_effect=run_pipeline)
    index = mocker.MagicMock(spec=MockIndexManager)
    index.update_status = mocker.AsyncMock()
    window = MainWindow(
        pipeline_runner=runner,
        log_bridge=log_bridge,
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=index,
    )
    show_path = tmp_path / "Stopped Show"
    _set_active_show(window, show_path, "Stopped Show")
    window._sidebar.add_show(
        ShowSummary(
            name="Stopped Show",
            path=show_path.resolve(),
            status=ShowStatus.READY,
            episode_count=1,
            processed_count=0,
            subtitle_text="1 episode found",
        )
    )

    first_task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await first_run_started.wait()
    window._on_stop_click()
    window._on_stop_click()
    await first_task
    assert window.run_button.isEnabled()

    await window._on_run_click.__wrapped__(window)

    events = [str(entry["event"]) for entry in log_bridge.get_session_log()]
    assert events.count("Pipeline stop requested") == 1
    assert events.count("Pipeline stopped by user") == 1
    assert "Pipeline failed" not in events
    assert (
        window.progress_panel.status_label.text() == "Pipeline executed successfully!"
    )

    from src.core.log_export import export_log_to_file

    export_path = tmp_path / "stop-sequence.txt"
    await export_log_to_file(log_bridge.get_session_log(), export_path)
    exported = export_path.read_text(encoding="utf-8")
    assert "Pipeline stop requested" in exported
    assert "Pipeline stopped by user" in exported


@pytest.mark.asyncio
async def test_main_window_real_overlapping_refresh(mocker, tmp_path: Path) -> None:
    """A second Refresh supersedes and joins the first one without stale output."""
    entered_scan_event = asyncio.Event()
    calls = 0

    async def mock_scan(*_args, **kwargs):
        nonlocal calls
        calls += 1
        entered_scan_event.set()
        if calls == 1:
            stop_event = kwargs["stop_event"]
            await stop_event.wait()
            raise PipelineStoppedError("superseded")
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

    task2 = asyncio.create_task(window._on_refresh_index.__wrapped__(window))
    await task2
    await task1

    assert mock_runner.library_scanner.scan.call_count == 2

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

    async def mock_scan(path: Path, **_kwargs: object) -> LibraryScanOutput:
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
    mock_runner.library_scanner.scan.assert_called_once()
    assert mock_runner.library_scanner.scan.call_args.args[0] == tmp_path


@pytest.mark.asyncio
async def test_main_window_add_folder_library_root_prevents_scan_and_warns(
    mocker, tmp_path: Path
) -> None:
    """Task 2: Selecting configured library root in Add Folder performs zero scans and shows QMessageBox."""
    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock()

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.add_show = mocker.AsyncMock()

    mock_msgbox = mocker.patch("PySide6.QtWidgets.QMessageBox.information")

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    await window._on_add_folder.__wrapped__(window, tmp_path)

    # Zero scans, zero index additions
    mock_runner.library_scanner.scan_folder.assert_not_called()
    mock_index.add_show.assert_not_called()
    assert window._sidebar._list_widget.count() == 0

    # User-facing explanation displayed
    mock_msgbox.assert_called_once_with(
        window,
        "Library Root Selected",
        "This is the configured library root. Use Refresh to rebuild the "
        "complete library index, or select one individual show folder.",
    )


@pytest.mark.asyncio
async def test_main_window_add_folder_library_root_windows_case_insensitive(
    mocker, tmp_path: Path
) -> None:
    """Task 2: Windows case variations of library root are safely matched."""
    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock()

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)

    mock_msgbox = mocker.patch("PySide6.QtWidgets.QMessageBox.information")

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    # Path variation with different case or slashes
    variant_path = Path(str(tmp_path).upper())
    await window._on_add_folder.__wrapped__(window, variant_path)

    mock_runner.library_scanner.scan_folder.assert_not_called()
    mock_msgbox.assert_called_once()


@pytest.mark.asyncio
async def test_main_window_add_folder_child_show_folder_scans_normally(
    mocker, tmp_path: Path
) -> None:
    """Task 2: Selecting a child show folder scans normally."""
    mock_runner = mocker.MagicMock()
    mock_scan_output = LibraryScanOutput(episodes=[], font_directories=[], show_tree=())
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        return_value=mock_scan_output
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.add_show = mocker.AsyncMock()

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
        show_index_manager=mock_index,
    )

    child_path = tmp_path / "SubShow"
    await window._on_add_folder.__wrapped__(window, child_path)

    mock_runner.library_scanner.scan_folder.assert_called_once()
    assert mock_runner.library_scanner.scan_folder.call_args.args[0] == child_path
    mock_index.add_show.assert_called_once()
    assert window._sidebar._list_widget.count() == 1


@pytest.mark.asyncio
async def test_main_window_add_folder_cancelled_dialog_is_a_no_op(
    mocker, tmp_path: Path
) -> None:
    """Cancelling Add Folder does not scan, index, or change the sidebar."""
    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.add_show = mocker.AsyncMock()
    mocker.patch.object(QFileDialog, "getExistingDirectory", return_value="")

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )

    await window._on_add_folder.__wrapped__(window)

    mock_runner.library_scanner.scan_folder.assert_not_called()
    mock_index.add_show.assert_not_called()
    assert window._sidebar._list_widget.count() == 0


@pytest.mark.asyncio
async def test_main_window_refresh_index_multi_show_tree(
    mocker, tmp_path: Path
) -> None:
    """Task 4: Full refresh converts show_tree with multiple top-level shows into separate ShowSummary rows."""
    from src.models.pipeline import EpisodeContext, ShowNode, SubFolderNode

    node1 = ShowNode(
        name="Bleach",
        path=tmp_path / "Bleach",
        sub_folders=(
            SubFolderNode(
                name="Season 2",
                path=tmp_path / "Bleach" / "Season 2",
                episodes=(
                    EpisodeContext(
                        scan_result=LibraryScanResult(
                            episode_path=tmp_path / "Bleach" / "Season 2" / "02.mkv",
                            anime_title="Bleach",
                        )
                    ),
                ),
            ),
        ),
        episodes=(
            EpisodeContext(
                scan_result=LibraryScanResult(
                    episode_path=tmp_path / "Bleach" / "01.mkv",
                    anime_title="Bleach",
                )
            ),
        ),
    )
    node2 = ShowNode(
        name="Naruto",
        path=tmp_path / "Naruto",
        sub_folders=(),
        episodes=(
            EpisodeContext(
                scan_result=LibraryScanResult(
                    episode_path=tmp_path / "Naruto" / "01.mkv",
                    anime_title="Naruto",
                )
            ),
            EpisodeContext(
                scan_result=LibraryScanResult(
                    episode_path=tmp_path / "Naruto" / "02.mkv",
                    anime_title="Naruto",
                )
            ),
        ),
    )

    mock_runner = mocker.MagicMock()
    mock_scan_output = LibraryScanOutput(
        episodes=[], font_directories=[], show_tree=(node1, node2)
    )
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

    # Sidebar receives two top-level ShowSummary rows, never one root "Anime" row.
    assert window._sidebar._list_widget.count() == 2
    saved_shows = mock_index.save.call_args.args[0]
    assert [(show.name, show.path, show.episode_count) for show in saved_shows] == [
        ("Bleach", tmp_path / "Bleach", 2),
        ("Naruto", tmp_path / "Naruto", 2),
    ]
    assert all(show.name != "Anime" for show in saved_shows)


def _scan_output(path: Path, name: str) -> LibraryScanOutput:
    return LibraryScanOutput(
        episodes=[LibraryScanResult(episode_path=path / "01.mkv", anime_title=name)],
        font_directories=[],
        show_tree=(),
    )


@pytest.mark.asyncio
async def test_main_window_show_selection_latest_request_wins(
    mocker, tmp_path: Path
) -> None:
    """A late scan result must not replace the most recent show selection."""
    show_a = tmp_path / "Show A"
    show_b = tmp_path / "Show B"
    a_started = asyncio.Event()

    async def scan_folder(
        path: Path, *, stop_event: asyncio.Event | None = None
    ) -> LibraryScanOutput:
        if path == show_a.resolve():
            a_started.set()
            assert stop_event is not None
            await stop_event.wait()
            raise PipelineStoppedError("superseded")
        return _scan_output(show_b, "Show B")

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(side_effect=scan_folder)
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )

    task_a = asyncio.create_task(
        window._on_show_selected.__wrapped__(window, "Show A", show_a)
    )
    await a_started.wait()
    await window._on_show_selected.__wrapped__(window, "Show B", show_b)
    await task_a

    assert window._current_show_path == show_b.resolve()
    assert window._current_show_name == "Show B"
    assert window.run_button.isEnabled() is True


@pytest.mark.asyncio
async def test_main_window_failed_current_selection_preserves_previous_show(
    mocker, tmp_path: Path
) -> None:
    """A current scan error keeps the last valid show and selection available."""
    from src.errors import AnimeStudioError

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(
        side_effect=AnimeStudioError("unreadable show")
    )
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )
    _set_active_show(window, tmp_path / "Old", "Old")

    await window._on_show_selected.__wrapped__(window, "Broken", tmp_path / "Broken")

    assert window._current_show_path == (tmp_path / "Old")
    assert window._current_show_name == "Old"
    assert window._episode_table.get_selected_paths()
    assert window.run_button.isEnabled() is True


@pytest.mark.asyncio
async def test_main_window_stale_selection_failure_cannot_replace_newer_success(
    mocker, tmp_path: Path
) -> None:
    """An older failed scan is discarded after a newer successful selection."""
    show_a = tmp_path / "Show A"
    show_b = tmp_path / "Show B"
    a_started = asyncio.Event()

    async def scan_folder(
        path: Path, *, stop_event: asyncio.Event | None = None
    ) -> LibraryScanOutput:
        if path == show_a.resolve():
            a_started.set()
            assert stop_event is not None
            await stop_event.wait()
            raise PipelineStoppedError("superseded")
        return _scan_output(show_b, "Show B")

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(side_effect=scan_folder)
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )

    task_a = asyncio.create_task(
        window._on_show_selected.__wrapped__(window, "Show A", show_a)
    )
    await a_started.wait()
    await window._on_show_selected.__wrapped__(window, "Show B", show_b)
    await task_a

    assert window._current_show_path == show_b.resolve()
    assert window._show_name_label.text() == "Show B"


@pytest.mark.asyncio
async def test_main_window_refresh_invalidates_active_show_and_late_scan(
    mocker, tmp_path: Path
) -> None:
    """Refresh clears active state and prevents an older folder scan from applying."""
    show_path = tmp_path / "Old"
    selection_started = asyncio.Event()
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    async def scan_folder(
        path: Path, *, stop_event: asyncio.Event | None = None
    ) -> LibraryScanOutput:
        selection_started.set()
        assert stop_event is not None
        await stop_event.wait()
        raise PipelineStoppedError("superseded")

    async def scan_library(path: Path, **_kwargs: object) -> LibraryScanOutput:
        refresh_started.set()
        await release_refresh.wait()
        return LibraryScanOutput(episodes=[], font_directories=[], show_tree=())

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(side_effect=scan_folder)
    mock_runner.library_scanner.scan = mocker.AsyncMock(side_effect=scan_library)
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.save = mocker.AsyncMock()
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )

    selection_task = asyncio.create_task(
        window._on_show_selected.__wrapped__(window, "Old", show_path)
    )
    await selection_started.wait()
    refresh_task = asyncio.create_task(window._on_refresh_index.__wrapped__(window))
    await refresh_started.wait()

    assert window._current_show_path is None
    assert window._episode_table.get_selected_paths() == []
    assert window.run_button.isEnabled() is False

    await selection_task
    release_refresh.set()
    await refresh_task

    assert window._current_show_path is None
    assert window.run_button.isEnabled() is False


@pytest.mark.asyncio
async def test_main_window_refresh_failure_preserves_previous_show(
    mocker, tmp_path: Path
) -> None:
    """A failed refresh must leave the prior valid show usable."""
    from src.errors import AnimeStudioError

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan = mocker.AsyncMock(
        side_effect=AnimeStudioError("refresh failed")
    )
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )
    _set_active_show(window, tmp_path / "Old", "Old")

    await window._on_refresh_index.__wrapped__(window)

    assert window._current_show_path == (tmp_path / "Old")
    assert window.run_button.isEnabled() is True


@pytest.mark.asyncio
async def test_main_window_add_folder_late_result_does_not_replace_selection(
    mocker, tmp_path: Path
) -> None:
    """A completed Add Folder scan is indexed but cannot overwrite newer selection UI."""
    add_path = tmp_path / "Added"
    show_b = tmp_path / "Show B"
    add_started = asyncio.Event()

    async def scan_folder(
        path: Path, *, stop_event: asyncio.Event | None = None
    ) -> LibraryScanOutput:
        if path == add_path.resolve():
            add_started.set()
            assert stop_event is not None
            await stop_event.wait()
            raise PipelineStoppedError("superseded")
        return _scan_output(show_b, "Show B")

    mock_runner = mocker.MagicMock()
    mock_runner.library_scanner.scan_folder = mocker.AsyncMock(side_effect=scan_folder)
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.add_show = mocker.AsyncMock()
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )

    add_task = asyncio.create_task(window._on_add_folder.__wrapped__(window, add_path))
    await add_started.wait()
    await window._on_show_selected.__wrapped__(window, "Show B", show_b)
    await add_task

    mock_index.add_show.assert_not_awaited()
    assert mock_runner.library_scanner.scan_folder.call_count == 2
    assert window._current_show_path == show_b.resolve()
    assert window._show_name_label.text() == "Show B"


@pytest.mark.asyncio
async def test_main_window_run_snapshots_show_and_locks_navigation(
    mocker, tmp_path: Path
) -> None:
    """Run config and persistent statuses retain Show A despite later UI mutation."""
    status_started = asyncio.Event()
    release_status = asyncio.Event()
    statuses: list[tuple[Path, ShowStatus]] = []

    async def update_status(path: Path, status: ShowStatus) -> None:
        statuses.append((path, status))
        if status is ShowStatus.PROCESSING:
            status_started.set()
            await release_status.wait()

    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(
        return_value=PipelineReport(
            run_timestamp=datetime.now(timezone.utc),
            duration_ms=1.0,
            anime_title="Show A",
            episodes=[],
            total_fonts_found=0,
            genuine_misses=[],
        )
    )
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.update_status = mocker.AsyncMock(side_effect=update_status)
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )
    show_a = tmp_path / "Show A"
    episode_a = _set_active_show(window, show_a, "Show A")
    window._sidebar.add_show(
        ShowSummary(
            name="Show A",
            path=show_a.resolve(),
            status=ShowStatus.READY,
            episode_count=1,
            processed_count=0,
            subtitle_text="1 episode found",
        )
    )
    runner_sidebar_statuses: list[ShowStatus] = []

    async def run_with_visible_processing(
        *_args: object, **_kwargs: object
    ) -> PipelineReport:
        show = window._sidebar._list_widget.item(0).data(Qt.ItemDataRole.UserRole)
        runner_sidebar_statuses.append(show.status)
        return mock_runner.run.return_value

    mock_runner.run.side_effect = run_with_visible_processing

    run_task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await status_started.wait()
    assert window._sidebar._list_widget.isEnabled() is False
    assert window._sidebar._add_btn.isEnabled() is False
    assert window._sidebar.is_refresh_enabled() is False
    assert (
        window._sidebar._list_widget.item(0).data(Qt.ItemDataRole.UserRole).status
        == ShowStatus.READY
    )

    window._invalidate_active_show()
    _set_active_show(window, tmp_path / "Show B", "Show B")
    release_status.set()
    await run_task

    config_arg = mock_runner.run.call_args.args[0]
    assert config_arg.discovery_root == show_a.resolve()
    assert config_arg.anime_title == "Show A"
    assert config_arg.selected_paths == frozenset({episode_a.resolve()})
    assert statuses == [
        (show_a.resolve(), ShowStatus.PROCESSING),
        (show_a.resolve(), ShowStatus.ALL_DONE),
    ]
    assert window._sidebar._list_widget.isEnabled() is True
    assert window._sidebar._add_btn.isEnabled() is True
    assert window._sidebar.is_refresh_enabled() is True
    # The original run is now stale, so its visible sidebar status must not
    # overwrite the newly selected show state.
    assert runner_sidebar_statuses == [ShowStatus.READY]


@pytest.mark.asyncio
async def test_main_window_run_failure_restores_navigation(
    mocker, tmp_path: Path
) -> None:
    """Navigation locking is restored through the run failure cleanup path."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def failing_run(*_args: object, **_kwargs: object) -> PipelineReport:
        started.set()
        await release.wait()
        raise RuntimeError("pipeline failed")

    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(side_effect=failing_run)
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.update_status = mocker.AsyncMock()
    mocker.patch("src.gui.widgets.error_dialog.show_error_dialog")
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )
    _set_active_show(window, tmp_path / "Show A", "Show A")

    task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await started.wait()
    assert window._sidebar._list_widget.isEnabled() is False
    release.set()
    await task

    assert window._sidebar._list_widget.isEnabled() is True
    assert window._sidebar._add_btn.isEnabled() is True
    assert window._sidebar.is_refresh_enabled() is True


@pytest.mark.asyncio
async def test_main_window_initial_processing_status_failure_restores_ui(
    mocker, tmp_path: Path
) -> None:
    """A failed initial status write reaches the same bounded run cleanup path."""
    from src.errors import AnimeStudioError

    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock()
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.update_status = mocker.AsyncMock(
        side_effect=AnimeStudioError("index unavailable")
    )
    error_dialog = mocker.patch("src.gui.widgets.error_dialog.show_error_dialog")
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )
    show_a = tmp_path / "Show A"
    _set_active_show(window, show_a, "Show A")
    window._sidebar.add_show(
        ShowSummary(
            name="Show A",
            path=show_a.resolve(),
            status=ShowStatus.READY,
            episode_count=1,
            processed_count=0,
            subtitle_text="1 episode found",
        )
    )
    original_status = (
        window._sidebar._list_widget.item(0).data(Qt.ItemDataRole.UserRole).status
    )

    await window._on_run_click.__wrapped__(window)

    mock_runner.run.assert_not_called()
    assert mock_index.update_status.await_count == 1
    assert (
        window._sidebar._list_widget.item(0).data(Qt.ItemDataRole.UserRole).status
        == original_status
    )
    assert original_status is not ShowStatus.PROCESSING
    assert window._pipeline_running is False
    assert window.stop_button.isVisible() is False
    assert window.stop_button.isEnabled() is True
    assert window._sidebar._list_widget.isEnabled() is True
    assert window._sidebar._add_btn.isEnabled() is True
    assert window._sidebar.is_refresh_enabled() is True
    assert window.run_button.isEnabled() is True
    error_dialog.assert_called_once()


@pytest.mark.asyncio
async def test_main_window_stale_run_does_not_update_newer_show_table(
    mocker, tmp_path: Path
) -> None:
    """Programmatic reentrancy cannot apply Show A results to visible Show B."""
    from src.models.report import EpisodeReport, EpisodeStatus

    status_started = asyncio.Event()
    release_status = asyncio.Event()
    persistent_statuses: list[tuple[Path, ShowStatus]] = []

    async def update_status(path: Path, status: ShowStatus) -> None:
        persistent_statuses.append((path, status))
        if status is ShowStatus.PROCESSING:
            status_started.set()
            await release_status.wait()

    show_a = tmp_path / "Show A"
    show_b = tmp_path / "Show B"
    episode_a = show_a / "01.mkv"
    report = PipelineReport(
        run_timestamp=datetime.now(timezone.utc),
        duration_ms=1.0,
        anime_title="Show A",
        episodes=[EpisodeReport(episode_path=episode_a, status=EpisodeStatus.COMPLETE)],
        total_fonts_found=0,
        genuine_misses=[],
    )
    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(return_value=report)
    mock_index = mocker.MagicMock(spec=MockIndexManager)
    mock_index.update_status = mocker.AsyncMock(side_effect=update_status)
    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=mock_index,
    )
    _set_active_show(window, show_a, "Show A")

    run_task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await status_started.wait()
    window._invalidate_active_show()
    window._display_scan_result(
        "Show B",
        show_b,
        _scan_output(show_b, "Show B"),
    )
    visible_update = mocker.spy(window._episode_table, "update_episode_status")

    release_status.set()
    await run_task

    assert window._current_show_path == show_b
    assert window._show_name_label.text() == "Show B"
    assert (
        str(
            window._episode_table._model.data(
                window._episode_table._model.index(0, 3),
                Qt.ItemDataRole.DisplayRole,
            )
        ).casefold()
        == "skipped"
    )
    visible_update.assert_not_called()
    assert persistent_statuses == [
        (show_a, ShowStatus.PROCESSING),
        (show_a, ShowStatus.ALL_DONE),
    ]


@pytest.mark.asyncio
async def test_main_window_folder_scan_cancel_is_visible_idempotent_and_neutral(
    mocker, tmp_path: Path
) -> None:
    """The actual Stop surface cancels a folder scan without a pipeline result."""
    show_path = tmp_path / "Show A"
    scan_started = asyncio.Event()

    async def scan_folder(
        path: Path, *, stop_event: asyncio.Event | None = None
    ) -> LibraryScanOutput:
        assert path == show_path.resolve()
        assert stop_event is not None
        scan_started.set()
        await stop_event.wait()
        raise PipelineStoppedError("folder stop")

    runner = mocker.MagicMock()
    runner.library_scanner.scan_folder = mocker.AsyncMock(side_effect=scan_folder)
    window = MainWindow(
        pipeline_runner=runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )

    task = asyncio.create_task(window._on_add_folder.__wrapped__(window, show_path))
    await scan_started.wait()
    assert not window.stop_button.isHidden()
    assert window.stop_button.text() == "Cancel scan"
    assert window.stop_button.accessibleName() == "Cancel scan"

    window._on_stop_click()
    assert window.stop_button.text() == "Stopping scan…"
    window._on_stop_click()
    await task

    assert window._active_scan is None
    assert window.progress_panel.status_label.text() == "Folder scan stopped"
    assert not window.stop_button.isVisible()
    assert window._sidebar._add_btn.isEnabled()
    assert window._sidebar.is_refresh_enabled()
    assert window.run_button.isEnabled() is False
    assert [entry["event"] for entry in window._log_bridge.get_session_log()] == [
        "Folder scan stop requested",
        "Folder scan stopped",
    ]


@pytest.mark.asyncio
async def test_main_window_close_requests_folder_scan_cleanup(
    mocker, tmp_path: Path
) -> None:
    """Closing a window requests scan stop and consumes the owned task."""
    show_path = tmp_path / "Show A"
    entered = asyncio.Event()

    async def scan_folder(
        _path: Path, *, stop_event: asyncio.Event | None = None
    ) -> LibraryScanOutput:
        assert stop_event is not None
        entered.set()
        await stop_event.wait()
        raise PipelineStoppedError("window closed")

    runner = mocker.MagicMock()
    runner.library_scanner.scan_folder = mocker.AsyncMock(side_effect=scan_folder)
    window = MainWindow(
        pipeline_runner=runner,
        log_bridge=MockLogBridge(),
        config=MockConfig(tmp_path),
        font_ingestion_service=mocker.MagicMock(),
        show_index_manager=MockIndexManager(tmp_path),
    )
    scan_task = asyncio.create_task(
        window._on_add_folder.__wrapped__(window, show_path)
    )
    await entered.wait()
    close_event = mocker.MagicMock()

    window.closeEvent(close_event)
    close_event.accept.assert_called_once()
    await scan_task
    assert window._close_scan_cleanup_task is not None
    await window._close_scan_cleanup_task
    assert window._active_scan is None
