import pytest
from PySide6.QtWidgets import QApplication
from src.gui.messages import ProgressStage, ProgressState
from src.gui.widgets.progress_panel import ProgressPanelWidget


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_progress_panel_initial_state() -> None:
    """Verify that ProgressPanelWidget starts with hidden state."""
    panel = ProgressPanelWidget()
    assert panel.isVisible() is False
    assert panel.status_label.text() == "Idle"


def test_progress_panel_idle_state() -> None:
    """Verify that update_state with ProgressStage.IDLE hides the widget."""
    panel = ProgressPanelWidget()
    panel.show()
    assert panel.isVisible() is True

    panel.update_state(ProgressState(stage=ProgressStage.IDLE))
    assert panel.isVisible() is False


def test_progress_panel_scanning_state() -> None:
    """Verify that update_state with ProgressStage.SCANNING sets indeterminate mode."""
    panel = ProgressPanelWidget()
    state = ProgressState(
        stage=ProgressStage.SCANNING, status_text="Locating anime files..."
    )

    panel.update_state(state)
    assert panel.isVisible() is True
    assert panel.status_label.text() == "Locating anime files..."
    assert panel.progress_bar.minimum() == 0
    assert panel.progress_bar.maximum() == 0


def test_progress_panel_muxing_state() -> None:
    """Verify that update_state with ProgressStage.MUXING sets determinate range and values."""
    panel = ProgressPanelWidget()
    state = ProgressState(stage=ProgressStage.MUXING, current=3, total=10)

    panel.update_state(state)
    assert panel.isVisible() is True
    assert panel.status_label.text() == "Muxing episode 3 of 10..."
    assert panel.progress_bar.minimum() == 0
    assert panel.progress_bar.maximum() == 10
    assert panel.progress_bar.value() == 3


def test_progress_panel_complete_state() -> None:
    """Verify that update_state with ProgressStage.COMPLETE uses success tokens."""
    panel = ProgressPanelWidget()
    state = ProgressState(stage=ProgressStage.COMPLETE, status_text="Done!")

    panel.update_state(state)
    assert panel.isVisible() is True
    assert panel.status_label.text() == "Done!"
    assert panel.progress_bar.value() == 100
    assert panel.progress_bar.property("progressState") == "success"
    assert panel.progress_bar.accessibleDescription() == "Done!"


def test_progress_panel_error_state() -> None:
    """Verify that update_state with ProgressStage.ERROR uses error tokens."""
    panel = ProgressPanelWidget()
    state = ProgressState(
        stage=ProgressStage.ERROR, status_text="Something went wrong!"
    )

    panel.update_state(state)
    assert panel.isVisible() is True
    assert panel.status_label.text() == "Something went wrong!"
    assert panel.progress_bar.value() == 100
    assert panel.progress_bar.property("progressState") == "error"


def test_progress_panel_stopped_state_is_neutral_and_accessible() -> None:
    """A user stop has a neutral visible state rather than success or error."""
    panel = ProgressPanelWidget()
    panel.update_state(
        ProgressState(stage=ProgressStage.STOPPED, status_text="Run stopped by user")
    )

    assert panel.isVisible() is True
    assert panel.status_label.text() == "Run stopped by user"
    assert panel.progress_bar.value() == 0
    assert panel.progress_bar.property("progressState") == "stopped"
    assert panel.status_label.accessibleDescription() == "Run stopped by user"
