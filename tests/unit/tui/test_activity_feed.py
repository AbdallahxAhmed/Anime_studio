import pytest
from datetime import datetime
from textual.app import App, ComposeResult
from textual.widgets import RichLog
from src.tui.widgets.activity_feed import ActivityFeed
from src.tui.messages import LogEntry


class DummyFeedApp(App):
    def compose(self) -> ComposeResult:
        yield ActivityFeed(id="feed")


@pytest.mark.asyncio
async def test_activity_feed_formatting():
    app = DummyFeedApp()
    async with app.run_test() as pilot:
        feed = app.query_one(ActivityFeed)
        rich_log = feed.query_one(RichLog)

        now = datetime(2026, 5, 26, 12, 0, 0)

        # Post INFO log
        feed.write_log(LogEntry(timestamp=now, level="info", event="Test info"))
        # Post WARNING log
        feed.write_log(LogEntry(timestamp=now, level="warning", event="Test warning"))
        # Post ERROR log
        feed.write_log(LogEntry(timestamp=now, level="error", event="Test error"))

        await pilot.pause()

        # Verify RichLog contains the logs
        # In Textual, rich_log.lines is a list of Strip objects
        assert len(rich_log.lines) == 3


@pytest.mark.asyncio
async def test_activity_feed_scroll_toggles_auto_scroll():
    from unittest.mock import patch, PropertyMock

    app = DummyFeedApp()
    async with app.run_test():
        feed = app.query_one(ActivityFeed)
        rich_log = feed.query_one(RichLog)

        # Initially auto_scroll is True
        assert rich_log.auto_scroll is True

        # Manually trigger on_scroll while max_scroll_y is 0
        feed.on_scroll()
        # Since scroll_y (0) == max_scroll_y (0), it should stay True
        assert rich_log.auto_scroll is True

        # Simulate user scrolled up by setting scroll_y < max_scroll_y (e.g. max_scroll_y=10, scroll_y=5)
        with (
            patch.object(
                RichLog, "max_scroll_y", new_callable=PropertyMock, return_value=10
            ),
            patch.object(
                RichLog, "scroll_y", new_callable=PropertyMock, return_value=5
            ),
        ):
            feed.on_scroll()
            # auto_scroll should be False now
            assert rich_log.auto_scroll is False

        # Scroll back to bottom (scroll_y == max_scroll_y)
        with (
            patch.object(
                RichLog, "max_scroll_y", new_callable=PropertyMock, return_value=10
            ),
            patch.object(
                RichLog, "scroll_y", new_callable=PropertyMock, return_value=10
            ),
        ):
            feed.on_scroll()
            # auto_scroll should be True again
            assert rich_log.auto_scroll is True
