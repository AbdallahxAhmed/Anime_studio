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
                yield Label("Anime Studio v3 - Muxing Dashboard", id="header-title")

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

            # Dry-run banner, visible only when dry-run is executing
            dry_run_banner = Static(
                "[DRY RUN] Simulated execution. No files will be modified.",
                id="dry-run-banner",
            )
            dry_run_banner.display = False
            yield dry_run_banner

            # Execution panel containing progress, activity feed, and results
            with Vertical(id="execution-container"):
                # Hide these initially
                progress = ProgressPanel(id="progress-panel")
                progress.display = False
                yield progress

                feed = ActivityFeed(id="activity-feed-panel")
                feed.display = False
                yield feed

                results = ResultsSummary(id="results-panel")
                results.display = False
                yield results

        yield Footer()

    def on_mount(self) -> None:
        # T021: Set up the 100ms timer to call log bridge's flush
        self.set_interval(0.1, self._flush_log_bridge)

    def _flush_log_bridge(self) -> None:
        """Throttled flush of the log bridge buffer."""
        if hasattr(self.app, "log_bridge") and self.app.log_bridge:
            self.app.log_bridge.flush()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle library path validation dynamically."""
        if event.input.id == "library-path":
            val = event.value.strip()
            run_btn = self.query_one("#run-pipeline", Button)
            # Enable button only if library path is specified
            run_btn.disabled = not bool(val)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle run pipeline or other buttons."""
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
                sync_enabled=True,  # Enable subtitle sync by default
            )
            self.dry_run = config.dry_run

            # Disable controls
            path_input.disabled = True
            event.button.disabled = True

            # Reset display states
            dry_run_banner = self.query_one("#dry-run-banner", Static)
            dry_run_banner.display = config.dry_run

            progress_panel = self.query_one("#progress-panel", ProgressPanel)
            progress_panel.display = True

            feed_panel = self.query_one("#activity-feed-panel", ActivityFeed)
            feed_panel.display = True

            results_panel = self.query_one("#results-panel", ResultsSummary)
            results_panel.display = False

            # Run pipeline in a background exclusive worker
            self.run_worker(self._run_pipeline(config), exclusive=True)

        elif event.button.id == "run-again":
            # Reset inputs and buttons
            path_input = self.query_one("#library-path", Input)
            path_input.value = ""
            path_input.disabled = False

            run_btn = self.query_one("#run-pipeline", Button)
            run_btn.disabled = True

            # Hide panels
            self.query_one("#results-panel", ResultsSummary).display = False
            self.query_one("#progress-panel", ProgressPanel).display = False
            self.query_one("#activity-feed-panel", ActivityFeed).display = False
            self.query_one("#dry-run-banner", Static).display = False

    async def _run_pipeline(self, config: PipelineConfig) -> None:
        """Worker task executing pipeline runner, handling success, ExceptionGroup and failures."""
        self.post_message(PipelineStarted())
        try:
            # Execute PipelineRunner
            report = await self.app.pipeline_runner.run(config)

            # Post completed message to self
            success = True
            if report.episodes:
                # Success if at least one episode succeeded or none failed catastrophically
                success = not any(ep.status == "failed" for ep in report.episodes)
            self.post_message(PipelineCompleted(report=report, success=success))

        except ExceptionGroup as eg:
            logger.error(
                "ExceptionGroup caught in TUI pipeline run", exceptions=eg.exceptions
            )
            # Python 3.11+ syntax to unwrap and post domain/non-domain errors
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
            # Re-enable inputs
            path_input = self.query_one("#library-path", Input)
            run_btn = self.query_one("#run-pipeline", Button)
            path_input.disabled = False
            run_btn.disabled = not bool(path_input.value.strip())

    def on_log_entry(self, message: LogEntry) -> None:
        """Forward LogEntry messages to the ActivityFeed widget."""
        try:
            feed = self.query_one("#activity-feed-panel", ActivityFeed)
            if getattr(self, "dry_run", False):
                message.context["dry_run"] = True
            feed.write_log(message)
        except Exception:
            pass

    def on_progress_update(self, message: ProgressUpdate) -> None:
        """Forward ProgressUpdate messages to the ProgressPanel widget."""
        try:
            progress = self.query_one("#progress-panel", ProgressPanel)
            progress.update_progress(message)
        except Exception:
            pass

    def on_pipeline_completed(self, message: PipelineCompleted) -> None:
        """Handle PipelineCompleted messages: show results panel, hide progress panel."""
        try:
            progress_panel = self.query_one("#progress-panel", ProgressPanel)
            progress_panel.display = False

            results_panel = self.query_one("#results-panel", ResultsSummary)
            results_panel.library_path = getattr(self, "library_path", None)
            results_panel.show_results(message.report)
            results_panel.display = True
        except Exception:
            pass

    def on_pipeline_error(self, message: PipelineError) -> None:
        """Handle PipelineError messages with custom modals or toasts."""
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
