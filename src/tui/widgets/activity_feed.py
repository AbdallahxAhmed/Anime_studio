from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import RichLog
from src.tui.messages import LogEntry


class ActivityFeed(Widget):
    """Widget displaying a formatted, real-time activity feed from pipeline logs."""

    def compose(self) -> ComposeResult:
        # Wraps RichLog with auto_scroll enabled by default
        yield RichLog(auto_scroll=True, id="activity-feed-log")

    def write_log(self, message: LogEntry) -> None:
        """Format and append a LogEntry message to the log with level-based color markup."""
        log_widget = self.query_one("#activity-feed-log", RichLog)

        # Format timestamp as HH:MM:SS
        time_str = message.timestamp.strftime("%H:%M:%S")

        level = message.level.lower()

        # Check if context has [DRY RUN] tags or prefixes
        prefix = ""
        if message.context.get("dry_run") or "[DRY RUN]" in message.event:
            prefix = "[DRY RUN] "

        event_text = f"{prefix}{message.event}"

        # Color coding based on log level
        if level == "warning":
            icon = "⚠"
            markup = f"[{time_str}] [yellow]{icon} {event_text}[/]"
        elif level in ("error", "critical"):
            icon = "✗"
            markup = f"[{time_str}] [red]{icon} {event_text}[/]"
        else:
            icon = "ℹ"
            markup = f"[{time_str}] {icon} {event_text}"

        log_widget.write(markup)

    def on_scroll(self) -> None:
        """Detect manual scroll to temporarily pause or resume auto-scroll behavior."""
        log_widget = self.query_one("#activity-feed-log", RichLog)
        # If the user has scrolled up from the bottom, pause auto-scroll to avoid disrupting their reading.
        # If they scroll back to the very bottom, re-enable auto-scroll.
        if log_widget.scroll_y < log_widget.max_scroll_y:
            log_widget.auto_scroll = False
        else:
            log_widget.auto_scroll = True
