from pathlib import Path
import structlog

from textual.screen import Screen
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Input, Checkbox, Button, Label, Static

from src.models.pipeline import PipelineConfig
from src.errors import AnimeStudioError, ToolNotFoundError
from src.tui.messages import (
    LogEntry,
    ProgressUpdate,
    PipelineStarted,
    PipelineCompleted,
    PipelineError,
)
from src.tui.widgets.activity_feed import ActivityFeed
from src.tui.widgets.progress_panel import ProgressPanel
from src.tui.widgets.results_summary import ResultsSummary
from src.tui.widgets.error_modal import ErrorModal

logger = structlog.get_logger()


class DashboardScreen(Screen):
    """Main dashboard screen for Anime Studio TUI."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            # Title Panel
            with Vertical(id="header-panel"):
                yield Label("Anime Studio v3 — Muxing Dashboard", id="header-title")

            # Input and settings panel
            with Vertical(id="input-panel"):
                yield Label("Library Path:")
                yield Input(
                    placeholder="Enter directory path containing MKVs and subtitles...",
                    id="library-path",
                )

                with Horizontal(id="controls-panel"):
                    yield Checkbox(
                        "Dry Run (No files modified)", value=False, id="dry-run"
                    )
                    yield Button(
                        "Run Pipeline",
                        variant="primary",
                        id="run-pipeline",
                        disabled=True,
                    )

            # Dry-run banner — hidden via CSS (display: none)
            yield Static(
                "[DRY RUN] Simulated execution. No files will be modified.",
                id="dry-run-banner",
            )

            # Execution panels — all hidden via CSS (display: none) until pipeline starts
            with Vertical(id="execution-container"):
                yield ProgressPanel(id="progress-panel")
                yield ActivityFeed(id="activity-feed-panel")
                yield ResultsSummary(id="results-panel")

        yield Footer()

    def on_mount(self) -> None:
        """Start the 100ms log bridge flush timer."""
        self._flush_timer = self.set_interval(0.1, self._flush_log_bridge)

    def _flush_log_bridge(self) -> None:
        """Drain buffered log bridge messages and post them to THIS screen."""
        if hasattr(self.app, "log_bridge") and self.app.log_bridge:
            bridge = self.app.log_bridge
            with bridge._lock:
                messages = list(bridge._buffer)
                bridge._buffer.clear()
            for msg in messages:
                self.post_message(msg)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Enable/disable Run button based on non-empty path."""
        if event.input.id == "library-path":
            val = event.value.strip()
            run_btn = self.query_one("#run-pipeline", Button)
            run_btn.disabled = not bool(val)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle run pipeline or run-again buttons."""
        if event.button.id == "run-pipeline":
            path_input = self.query_one("#library-path", Input)
            dry_run_cb = self.query_one("#dry-run", Checkbox)

            path_str = path_input.value.strip()
            if not path_str:
                return

            self.library_path = Path(path_str).resolve()

            config = PipelineConfig(
                library_path=self.library_path,
                dry_run=dry_run_cb.value,
                sync_enabled=True,
            )
            self.dry_run = config.dry_run

            # Disable controls during run
            path_input.disabled = True
            event.button.disabled = True

            # Show/hide panels for execution state
            self.query_one("#dry-run-banner", Static).display = config.dry_run
            self.query_one("#progress-panel", ProgressPanel).display = True
            self.query_one("#activity-feed-panel", ActivityFeed).display = True
            self.query_one("#results-panel", ResultsSummary).display = False

            # Launch worker
            self.run_worker(self._run_pipeline(config), exclusive=True)

        elif event.button.id == "run-again":
            path_input = self.query_one("#library-path", Input)
            path_input.value = ""
            path_input.disabled = False

            run_btn = self.query_one("#run-pipeline", Button)
            run_btn.disabled = True

            # Reset all execution panels to hidden
            self.query_one("#results-panel", ResultsSummary).display = False
            self.query_one("#progress-panel", ProgressPanel).display = False
            self.query_one("#activity-feed-panel", ActivityFeed).display = False
            self.query_one("#dry-run-banner", Static).display = False

    async def _run_pipeline(self, config: PipelineConfig) -> None:
        """Background worker: run pipeline, post lifecycle messages to THIS screen."""
        self.post_message(PipelineStarted())
        self.app.notify("Pipeline started…", severity="information")
        try:
            report = await self.app.pipeline_runner.run(config)

            success = True
            if report.episodes:
                success = not any(ep.status == "failed" for ep in report.episodes)
            self.post_message(PipelineCompleted(report=report, success=success))

        except ExceptionGroup as eg:
            logger.error(
                "ExceptionGroup caught in TUI pipeline run", exceptions=eg.exceptions
            )
            domain_errors, non_domain_errors = eg.split(AnimeStudioError)

            if domain_errors:
                for de in domain_errors.exceptions:
                    self.post_message(PipelineError(error=de, fatal=True))
            if non_domain_errors:
                for nde in non_domain_errors.exceptions:
                    logger.error("Fatal non-domain error inside group", error=str(nde))
                    self.post_message(PipelineError(error=nde, fatal=True))

        except AnimeStudioError as ase:
            logger.warning("Domain error in TUI pipeline run", error=str(ase))
            self.post_message(PipelineError(error=ase, fatal=True))

        except Exception as e:
            logger.error("Fatal exception in TUI pipeline run", error=str(e))
            self.post_message(PipelineError(error=e, fatal=True))

        finally:
            path_input = self.query_one("#library-path", Input)
            run_btn = self.query_one("#run-pipeline", Button)
            path_input.disabled = False
            run_btn.disabled = not bool(path_input.value.strip())

    # ── Message Handlers ──

    def on_log_entry(self, message: LogEntry) -> None:
        """Forward LogEntry to ActivityFeed widget."""
        try:
            feed = self.query_one("#activity-feed-panel", ActivityFeed)
            if getattr(self, "dry_run", False):
                message.context["dry_run"] = True
            feed.write_log(message)
        except Exception:
            pass

    def on_progress_update(self, message: ProgressUpdate) -> None:
        """Forward ProgressUpdate to ProgressPanel widget."""
        try:
            progress = self.query_one("#progress-panel", ProgressPanel)
            progress.update_progress(message)
        except Exception:
            pass

    def on_pipeline_completed(self, message: PipelineCompleted) -> None:
        """Show results, hide progress."""
        try:
            self.query_one("#progress-panel", ProgressPanel).display = False

            results_panel = self.query_one("#results-panel", ResultsSummary)
            results_panel.library_path = getattr(self, "library_path", None)
            results_panel.show_results(message.report)
            results_panel.display = True
        except Exception:
            pass

    def on_pipeline_error(self, message: PipelineError) -> None:
        """Map errors to modals or toasts."""
        try:
            error = message.error
            if isinstance(error, ToolNotFoundError):
                self.app.push_screen(
                    ErrorModal(
                        title="Critical Dependency Missing",
                        message=str(error),
                        suggestion="Please install the required tools using Scoop or manual installation.",
                    )
                )
            elif isinstance(error, AnimeStudioError):
                self.app.notify(str(error), severity="error", title="Pipeline Error")
            else:
                self.app.push_screen(
                    ErrorModal(
                        title="Fatal Unhandled Exception",
                        message=f"{error.__class__.__name__}: {str(error)}",
                        suggestion="Check the log feed or log files for technical details.",
                    )
                )
        except Exception:
            pass
