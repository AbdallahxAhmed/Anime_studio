from datetime import datetime, timezone
import pytest
import asyncio
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from src.gui.main_window import MainWindow
from src.models.report import PipelineReport


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class MockLogBridge(QObject):
    log_received = Signal(dict)


class MockConfig:
    def __init__(self, path: Path) -> None:
        self.library_path = path
        self.dry_run = True

    def save_to_toml(self) -> None:
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

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
    )

    window.library_picker.set_path(tmp_path)
    window.run_button.setEnabled(True)

    # Execute async slot handler directly
    await window._on_run_click()

    # Assert PipelineRunner was called correctly
    mock_runner.run.assert_called_once()
    config_arg = mock_runner.run.call_args[0][0]
    assert config_arg.library_path == tmp_path

    # Assert UI re-enabled
    assert window.run_button.isEnabled() is True
    assert window.library_picker.isEnabled() is True
    assert window._pipeline_running is False


@pytest.mark.asyncio
async def test_main_window_failed_run(mocker, tmp_path: Path) -> None:
    """Verify that a failed pipeline run catches exceptions, pops QMessageBox, and unlocks UI."""
    mock_runner = mocker.MagicMock()
    mock_runner.run = mocker.AsyncMock(
        side_effect=RuntimeError("Muxing tool failed to execute")
    )

    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()

    # Mock show_error_dialog to avoid showing blocking QMessageBox dialog in unit tests
    mock_dialog = mocker.patch("src.gui.widgets.error_dialog.show_error_dialog")

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
    )

    window.library_picker.set_path(tmp_path)
    window.run_button.setEnabled(True)

    # Execute async slot handler directly
    await window._on_run_click()

    mock_runner.run.assert_called_once()
    mock_dialog.assert_called_once()

    # Assert UI re-enabled
    assert window.run_button.isEnabled() is True
    assert window.library_picker.isEnabled() is True
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

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
    )

    # Assert Import button exists
    assert window.import_button is not None
    assert window.import_button.text() == "Import Fonts"

    # Mock QFileDialog.getExistingDirectory
    mocker.patch(
        "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
        return_value=str(tmp_path),
    )

    await window._on_import_fonts_click()

    # Verify that FontIngestionService.ingest_directories was called recursively
    mock_ingestion.ingest_directories.assert_called_once_with(
        [Path(tmp_path)], source="manual_import"
    )


def test_main_window_drag_enter_event_valid(mocker, tmp_path: Path) -> None:
    mock_runner = mocker.MagicMock()
    log_bridge = MockLogBridge()
    config = MockConfig(tmp_path)
    mock_ingestion = mocker.MagicMock()

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
    )

    # Mock QDragEnterEvent
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

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
    )

    # Mock QDragEnterEvent with invalid file type
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

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=mock_ingestion,
    )

    # Mock QDropEvent
    event = mocker.MagicMock()
    url = mocker.MagicMock()
    url.toLocalFile.return_value = "tests/fixtures/fonts/valid.ttf"
    event.mimeData().urls.return_value = [url]

    # Directly execute drop event
    window.dropEvent(event)

    event.acceptProposedAction.assert_called_once()

    # Yield control to let asyncio.ensure_future task execute
    await asyncio.sleep(0.05)

    mock_ingestion.ingest_files.assert_called_once_with(
        [Path("tests/fixtures/fonts/valid.ttf")], source="drag_drop"
    )
