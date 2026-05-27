from src.gui.log_bridge import GuiLogBridge


def test_gui_log_bridge_filters_and_emits() -> None:
    """Verify GuiLogBridge filters log events and emits thread-safe signals."""
    bridge = GuiLogBridge()
    emitted = []

    bridge.log_received.connect(emitted.append)

    # 1. Debug level should NOT be emitted
    bridge(None, "debug", {"event": "debug event", "level": "debug"})
    assert len(emitted) == 0

    # 2. Info level should be emitted
    bridge(None, "info", {"event": "info event", "level": "info"})
    assert len(emitted) == 1
    assert emitted[0]["event"] == "info event"
    assert emitted[0]["level"] == "info"

    # 3. Capitalized level should be normalized and emitted
    bridge(None, "warning", {"event": "warn event", "level": "WARNING"})
    assert len(emitted) == 2
    assert emitted[1]["level"] == "warning"
