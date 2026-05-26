import pytest
from datetime import datetime
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Label, DataTable
from src.tui.widgets.results_summary import ResultsSummary
from src.models.report import PipelineReport, EpisodeReport, EpisodeStatus


class DummyResultsApp(App):
    def compose(self) -> ComposeResult:
        yield ResultsSummary(id="results")


@pytest.mark.asyncio
async def test_results_summary_displays_correct_info():
    app = DummyResultsApp()
    async with app.run_test() as pilot:
        results = app.query_one(ResultsSummary)

        # Configure library_path
        results.library_path = Path("D:\\AnimeProject")

        # Mock PipelineReport
        now = datetime(2026, 5, 26, 12, 0, 0)
        report = PipelineReport(
            run_timestamp=now,
            duration_ms=150.5,
            anime_title="Epic Show",
            episodes=[
                EpisodeReport(
                    episode_path=Path("D:\\AnimeProject\\ep01.mkv"),
                    status=EpisodeStatus.COMPLETE,
                    missing_fonts=[],
                ),
                EpisodeReport(
                    episode_path=Path("D:\\AnimeProject\\ep02.mkv"),
                    status=EpisodeStatus.PARTIAL,
                    missing_fonts=["Arial Bold", "Times New Roman"],
                ),
            ],
            total_fonts_found=15,
            genuine_misses=["Arial Bold"],
        )

        results.show_results(report)
        await pilot.pause()

        # Verify Labels
        summary_lbl = results.query_one("#results-summary-info", Label)
        path_lbl = results.query_one("#results-path-label", Label)

        assert "Total Fonts Found: 15" in str(summary_lbl.render())
        assert "Genuine Misses: 1" in str(summary_lbl.render())
        assert "Duration: 150.5ms" in str(summary_lbl.render())

        # Verify absolute path resolution per T030 CONSTRAINT
        expected_path = Path("D:\\AnimeProject\\_AnimeStudio_Report.md").resolve()
        assert f"Report: {expected_path}" in str(path_lbl.render())

        # Verify DataTable
        table = results.query_one("#results-table", DataTable)
        assert table.row_count == 2

        # Verify row 1 contents: COMPLETE status
        row1 = table.get_row_at(0)
        assert row1[0] == "ep01.mkv"
        assert row1[1] == "✓"
        assert row1[2] == "None"

        # Verify row 2 contents: PARTIAL status
        row2 = table.get_row_at(1)
        assert row2[0] == "ep02.mkv"
        assert row2[1] == "⚠"
        assert row2[2] == "Arial Bold, Times New Roman"
