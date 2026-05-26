import pytest
from src.tui.log_bridge import LogBridge
from src.tui.messages import LogEntry, ProgressUpdate
from tests.unit.tui.test_messages import DummyApp


def test_log_bridge_filters_and_buffers():
    app = DummyApp()
    bridge = LogBridge(app)

    # Ignore DEBUG log
    bridge(None, "debug", {"event": "Debug message", "level": "debug"})
    # INFO log should be buffered
    bridge(None, "info", {"event": "Info message", "level": "info"})
    # WARNING log should be buffered
    bridge(None, "warning", {"event": "Warning message", "level": "warning"})
    # ERROR log should be buffered
    bridge(None, "error", {"event": "Error message", "level": "error"})

    # Check buffer contains the 3 INFO+ logs
    with bridge._lock:
        buffered = list(bridge._buffer)
    assert len(buffered) == 3
    assert all(isinstance(m, LogEntry) for m in buffered)
    assert buffered[0].event == "Info message"
    assert buffered[1].event == "Warning message"
    assert buffered[2].event == "Error message"


def test_log_bridge_progress_keys():
    app = DummyApp()
    bridge = LogBridge(app)

    # Log with progress keys
    bridge(
        None,
        "info",
        {
            "event": "Muxing episode 1",
            "level": "info",
            "progress_current": 1,
            "progress_total": 5,
            "stage": "mux",
        },
    )

    with bridge._lock:
        buffered = list(bridge._buffer)
    assert len(buffered) == 1
    assert isinstance(buffered[0], ProgressUpdate)
    assert buffered[0].stage == "mux"
    assert buffered[0].current == 1
    assert buffered[0].total == 5
    assert buffered[0].label == "Muxing episode 1"


@pytest.mark.asyncio
async def test_log_bridge_flush():
    app = DummyApp()
    bridge = LogBridge(app)

    # Put some logs
    bridge(None, "info", {"event": "Event 1", "level": "info"})
    bridge(None, "info", {"event": "Event 2", "level": "info"})

    async with app.run_test() as pilot:
        # Flush the bridge
        flushed = bridge.flush()
        assert len(flushed) == 2

        # Verify bridge buffer is empty
        with bridge._lock:
            assert len(bridge._buffer) == 0

        # Wait for messages to be processed by the app
        await pilot.pause()
        assert len(app.received_messages) == 2
        assert app.received_messages[0].event == "Event 1"
        assert app.received_messages[1].event == "Event 2"


def test_log_bridge_throttle_buffer_preservation():
    """Verify that a large number of messages (e.g. 15) are all preserved in the buffer and not dropped."""
    app = DummyApp()
    bridge = LogBridge(app)

    # Log 15 messages rapidly
    for i in range(15):
        bridge(None, "info", {"event": f"Log {i}", "level": "info"})

    with bridge._lock:
        assert len(bridge._buffer) == 15

    # Flush them all
    flushed = bridge.flush()
    assert len(flushed) == 15
    for i, msg in enumerate(flushed):
        assert msg.event == f"Log {i}"
