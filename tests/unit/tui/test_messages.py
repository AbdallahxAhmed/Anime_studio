from datetime import datetime
import pytest
from textual.app import App, ComposeResult
from textual.widgets import Label
from src.tui.messages import (
    LogEntry,
    ProgressUpdate,
    PipelineStarted,
    PipelineCompleted,
    PipelineError,
)
from src.models.report import PipelineReport
from src.errors import AnimeStudioError


class DummyApp(App):
    """A dummy app to verify message delivery."""

    def __init__(self) -> None:
        super().__init__()
        self.received_messages = []

    def compose(self) -> ComposeResult:
        yield Label("Test Label", id="test-label")

    def on_log_entry(self, message: LogEntry) -> None:
        self.received_messages.append(message)

    def on_progress_update(self, message: ProgressUpdate) -> None:
        self.received_messages.append(message)

    def on_pipeline_started(self, message: PipelineStarted) -> None:
        self.received_messages.append(message)

    def on_pipeline_completed(self, message: PipelineCompleted) -> None:
        self.received_messages.append(message)

    def on_pipeline_error(self, message: PipelineError) -> None:
        self.received_messages.append(message)


@pytest.mark.asyncio
async def test_message_subclasses_properties():
    # Test LogEntry construction
    now = datetime.now()
    log_msg = LogEntry(
        timestamp=now, level="info", event="Scan started", context={"custom": "value"}
    )
    assert log_msg.timestamp == now
    assert log_msg.level == "info"
    assert log_msg.event == "Scan started"
    assert log_msg.context == {"custom": "value"}

    # Test ProgressUpdate construction
    prog_msg = ProgressUpdate(
        stage="scan", current=2, total=10, label="Scanning files..."
    )
    assert prog_msg.stage == "scan"
    assert prog_msg.current == 2
    assert prog_msg.total == 10
    assert prog_msg.label == "Scanning files..."

    # Test PipelineStarted
    start_msg = PipelineStarted()
    assert start_msg is not None

    # Test PipelineCompleted
    mock_report = PipelineReport(
        run_timestamp=now,
        duration_ms=120.5,
        anime_title="Test Anime",
        episodes=[],
        total_fonts_found=5,
        genuine_misses=[],
    )
    comp_msg = PipelineCompleted(report=mock_report, success=True)
    assert comp_msg.report == mock_report
    assert comp_msg.success is True

    # Test PipelineError
    err = AnimeStudioError("Fatal error")
    err_msg = PipelineError(error=err, fatal=True)
    assert err_msg.error == err
    assert err_msg.fatal is True


@pytest.mark.asyncio
async def test_message_post_receive():
    app = DummyApp()
    async with app.run_test() as pilot:
        now = datetime.now()
        log_msg = LogEntry(timestamp=now, level="info", event="Test log")
        app.post_message(log_msg)
        await pilot.pause()
        assert len(app.received_messages) == 1
        assert isinstance(app.received_messages[0], LogEntry)
        assert app.received_messages[0].event == "Test log"

        prog_msg = ProgressUpdate(
            stage="scan", current=None, total=None, label="scanning"
        )
        app.post_message(prog_msg)
        await pilot.pause()
        assert len(app.received_messages) == 2
        assert isinstance(app.received_messages[1], ProgressUpdate)

        app.post_message(PipelineStarted())
        await pilot.pause()
        assert len(app.received_messages) == 3
        assert isinstance(app.received_messages[2], PipelineStarted)

        mock_report = PipelineReport(
            run_timestamp=now,
            duration_ms=10.0,
            anime_title="Test Anime",
            episodes=[],
            total_fonts_found=0,
            genuine_misses=[],
        )
        app.post_message(PipelineCompleted(report=mock_report, success=True))
        await pilot.pause()
        assert len(app.received_messages) == 4
        assert isinstance(app.received_messages[3], PipelineCompleted)

        app.post_message(PipelineError(error=Exception("Ouch"), fatal=True))
        await pilot.pause()
        assert len(app.received_messages) == 5
        assert isinstance(app.received_messages[4], PipelineError)
