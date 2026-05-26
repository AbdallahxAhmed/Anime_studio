from pathlib import Path
from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Label, DataTable, Button
from src.models.report import PipelineReport, EpisodeStatus


class ResultsSummary(Widget):
    """Widget displaying a detailed summary of episodes, status icons, font stats, and report path."""

    def __init__(self, **kwargs) -> None:
        self.library_path: Path | None = None
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Label("Pipeline Run Results", id="results-title")
        yield DataTable(id="results-table")
        yield Label("", id="results-summary-info")
        yield Label("", id="results-path-label")
        yield Button("Run Again", id="run-again", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.cursor_type = "row"

    def show_results(self, report: PipelineReport) -> None:
        """Populates the results summary widgets and DataTable from a PipelineReport."""
        table = self.query_one("#results-table", DataTable)
        table.clear(columns=True)

        # Add columns
        table.add_columns("Episode", "Status", "Fonts Missing")

        for ep in report.episodes:
            # Map status to styled icons
            status = ep.status
            if status == EpisodeStatus.COMPLETE:
                icon = "✓"
            elif status == EpisodeStatus.PARTIAL:
                icon = "⚠"
            elif status == EpisodeStatus.FAILED:
                icon = "✗"
            else:
                icon = "⏭"  # Skipped

            fonts_missing = ", ".join(ep.missing_fonts) if ep.missing_fonts else "None"
            table.add_row(Path(ep.episode_path).name, icon, fonts_missing)

        # Update stats label
        stats_lbl = self.query_one("#results-summary-info", Label)
        stats_lbl.update(
            f"Total Fonts Found: {report.total_fonts_found} | Genuine Misses: {len(report.genuine_misses)} | Duration: {report.duration_ms:.1f}ms"
        )

        # Update absolute report path label
        path_lbl = self.query_one("#results-path-label", Label)
        if self.library_path:
            abs_report_path = (
                Path(self.library_path).resolve() / "_AnimeStudio_Report.md"
            ).resolve()
            path_lbl.update(f"Report: {abs_report_path}")
        else:
            path_lbl.update("Report generated successfully.")
