from src.gui.signals import SignalBridge


def test_signal_bridge_emits() -> None:
    """Verify SignalBridge can emit custom typed signals without QApplication."""
    bridge = SignalBridge()
    received_data = []

    def log_handler(data: dict) -> None:
        received_data.append(data)

    bridge.log_received.connect(log_handler)
    test_dict = {"event": "hello", "level": "info"}
    bridge.log_received.emit(test_dict)

    assert len(received_data) == 1
    assert received_data[0] == test_dict
