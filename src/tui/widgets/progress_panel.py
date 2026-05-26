from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Label, ProgressBar, LoadingIndicator
from src.tui.messages import ProgressUpdate


class ProgressPanel(Widget):
    """Widget displaying active pipeline stage, loading spinner, and determinate progress bar."""

    def compose(self) -> ComposeResult:
        yield Label("Ready to scan", id="progress-stage")
        yield LoadingIndicator(id="progress-loading")
        yield ProgressBar(id="progress-bar")
        yield Label("", id="progress-detail")

    def on_mount(self) -> None:
        # Hide loading and progress bar initially
        self.query_one("#progress-loading", LoadingIndicator).display = False
        self.query_one("#progress-bar", ProgressBar).display = False

    def update_progress(self, message: ProgressUpdate) -> None:
        """Update progress states based on ProgressUpdate stage and values."""
        stage_lbl = self.query_one("#progress-stage", Label)
        loading_ind = self.query_one("#progress-loading", LoadingIndicator)
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        detail_lbl = self.query_one("#progress-detail", Label)

        stage = message.stage.lower()

        if stage == "scan":
            stage_lbl.update("Scanning Library...")
            loading_ind.display = True
            progress_bar.display = False
            detail_lbl.update(message.label)

        elif stage == "mux":
            stage_lbl.update("Muxing Episodes...")
            loading_ind.display = False
            progress_bar.display = True

            # Set values
            current = message.current if message.current is not None else 0
            total = message.total if message.total is not None else 1

            progress_bar.total = total
            progress_bar.progress = current

            detail_lbl.update(f"Muxing: {current}/{total} episodes - {message.label}")

        elif stage == "done":
            stage_lbl.update("Pipeline Complete! ✓")
            loading_ind.display = False
            progress_bar.display = True

            total = message.total if message.total is not None else 1
            progress_bar.total = total
            progress_bar.progress = total

            detail_lbl.update("All episodes muxed and processed successfully! ✓")
