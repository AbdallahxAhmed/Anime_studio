from textual.app import App, ComposeResult
from src.core.pipeline_runner import PipelineRunner
from src.tui.screens.dashboard import DashboardScreen


class AnimeStudioApp(App):
    """Main Textual App for Anime Studio TUI."""

    CSS_PATH = "styles/dashboard.tcss"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle Dark Mode"),
    ]

    def __init__(self, pipeline_runner: PipelineRunner) -> None:
        self.pipeline_runner = pipeline_runner
        self.log_bridge = None
        super().__init__()

    def compose(self) -> ComposeResult:
        yield DashboardScreen()
