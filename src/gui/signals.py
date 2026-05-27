from PySide6.QtCore import QObject, Signal


class SignalBridge(QObject):
    """Bridge for emitting signals from async coroutines/pipelines to PySide6 slots."""

    # Emitted when a structlog log event is received
    log_received = Signal(dict)

    # Emitted with a ProgressState model to update progress display
    progress_updated = Signal(object)

    # Emitted with a PipelineRunResult model when the pipeline finishes successfully
    pipeline_finished = Signal(object)

    # Emitted with a string error message when the pipeline fails
    pipeline_error = Signal(str)
