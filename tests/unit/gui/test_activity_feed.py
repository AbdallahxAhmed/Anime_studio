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


def test_activity_feed_initial_state() -> None:
    """Verify that ActivityFeedWidget starts with correct defaults."""
    feed = ActivityFeedWidget()
    assert feed.log_display.isReadOnly() is True
    assert feed.log_display.isUndoRedoEnabled() is False
    assert feed.log_display.document().maximumBlockCount() == 1000
    assert feed.log_display.toPlainText() == ""


def test_activity_feed_add_entries() -> None:
    """Verify log entries are correctly added and displayed."""
    feed = ActivityFeedWidget()
    
    feed.add_entry({"level": "info", "event": "Pipeline starting...", "timestamp": "2026-05-27T10:00:00Z"})
    feed.add_entry({"level": "warning", "event": "Font resolver mismatch", "timestamp": "2026-05-27T10:00:05Z"})
    feed.add_entry({"level": "error", "event": "Mux job failed", "timestamp": "2026-05-27T10:00:10Z"})
    feed.add_entry({"level": "debug", "event": "Debug context details", "timestamp": "2026-05-27T10:00:15Z"})

    content = feed.log_display.toPlainText()
    assert "[10:00:00] [INFO] Pipeline starting..." in content
    assert "[10:00:05] [WARNING] Font resolver mismatch" in content
    assert "[10:00:10] [ERROR] Mux job failed" in content
    assert "[10:00:15] [DEBUG] Debug context details" in content


def test_activity_feed_maximum_block_count_limit() -> None:
    """Verify the document limits number of stored log blocks to prevent memory leaks."""
    feed = ActivityFeedWidget()
    
    # Append 1050 logs
    for i in range(1050):
        feed.add_entry({"level": "info", "event": f"Log entry {i}"})

    # Total blocks should be capped exactly at 1000
    assert feed.log_display.document().blockCount() == 1000
    # First few entries should have been evicted, last entries should be present
    content = feed.log_display.toPlainText()
    assert "Log entry 0" not in content
    assert "Log entry 1049" in content


def test_activity_feed_clear() -> None:
    """Verify clear button clears logs."""
    feed = ActivityFeedWidget()
    feed.add_entry({"level": "info", "event": "Message"})
    assert "Message" in feed.log_display.toPlainText()

    feed.clear_button.click()
    assert feed.log_display.toPlainText() == ""


def test_activity_feed_collapsed_state_by_default() -> None:
    """Verify that ActivityFeedWidget is collapsed by default (maximumHeight == 36)."""
    feed = ActivityFeedWidget()
    assert feed.maximumHeight() == 36
    assert feed._is_collapsed is True


def test_activity_feed_toggle_expand_and_collapse() -> None:
    """Verify that toggle_collapsed() expands to 160px and collapses back to 36px."""
    feed = ActivityFeedWidget()
    
    # Expand
    feed.toggle_collapsed()
    assert feed.maximumHeight() == 160
    assert feed._is_collapsed is False

    # Collapse
    feed.toggle_collapsed()
    assert feed.maximumHeight() == 36
    assert feed._is_collapsed is True


def test_activity_feed_update_summary() -> None:
    """Verify update_summary() changes the summary label text."""
    feed = ActivityFeedWidget()
    feed.update_summary("Last event message")
    assert feed.summary_label.text() == "Last event message"

