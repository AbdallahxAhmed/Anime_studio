from textual.app import App
from src.core.pipeline_runner import PipelineRunner
from src.tui.screens.dashboard import DashboardScreen


class AnimeStudioApp(App):
    """Main Textual App for Anime Studio TUI."""

    CSS_PATH = "styles/dashboard.tcss"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle Dark Mode"),
    ]

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())

    def __init__(self, pipeline_runner: PipelineRunner) -> None:
        self.pipeline_runner = pipeline_runner
        self.log_bridge = None
        super().__init__()
