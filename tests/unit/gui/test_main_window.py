from datetime import datetime, timezone
import pytest
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

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
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

    # Mock show_error_dialog to avoid showing blocking QMessageBox dialog in unit tests
    mock_dialog = mocker.patch("src.gui.widgets.error_dialog.show_error_dialog")

    window = MainWindow(
        pipeline_runner=mock_runner,
        log_bridge=log_bridge,
        config=config,
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
