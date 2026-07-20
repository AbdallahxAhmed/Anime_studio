import pytest
from PySide6.QtWidgets import QApplication
from src.gui.widgets.activity_feed import ActivityFeedWidget


@pytest.fixture(scope="session", autouse=True)
def q_app() -> QApplication:
    """Ensure a QApplication instance exists for GUI unit testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_activity_feed_has_export_button() -> None:
    """Verify that ActivityFeedWidget has an export button."""
    feed = ActivityFeedWidget()
    assert feed.export_button is not None
    assert feed.export_button.text() == "Export Log"


def test_export_button_emits_signal() -> None:
    """Verify that clicking the export button emits the export_requested signal."""
    feed = ActivityFeedWidget()
    emitted = False

    def handler():
        nonlocal emitted
        emitted = True

    feed.export_requested.connect(handler)
    feed.export_button.click()
    assert emitted is True
