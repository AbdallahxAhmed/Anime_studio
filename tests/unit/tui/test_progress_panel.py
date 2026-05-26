import pytest
from textual.app import App, ComposeResult
from src.tui.widgets.progress_panel import ProgressPanel
from src.tui.messages import ProgressUpdate
from textual.widgets import Label, ProgressBar, LoadingIndicator


class DummyProgressApp(App):
    def compose(self) -> ComposeResult:
        yield ProgressPanel(id="progress")


@pytest.mark.asyncio
async def test_progress_panel_states():
    app = DummyProgressApp()
    async with app.run_test() as pilot:
        panel = app.query_one(ProgressPanel)

        stage_lbl = panel.query_one("#progress-stage", Label)
        loading_ind = panel.query_one("#progress-loading", LoadingIndicator)
        progress_bar = panel.query_one("#progress-bar", ProgressBar)
        detail_lbl = panel.query_one("#progress-detail", Label)

        # 1. Indeterminate scan mode
        panel.update_progress(
            ProgressUpdate(
                stage="scan", current=None, total=None, label="Scanning directory..."
            )
        )
        await pilot.pause()

        assert str(stage_lbl.render()) == "Scanning Library..."
        assert loading_ind.display is True
        assert progress_bar.display is False
        assert str(detail_lbl.render()) == "Scanning directory..."

        # 2. Determinate mux mode
        panel.update_progress(
            ProgressUpdate(stage="mux", current=3, total=12, label="Episode 3")
        )
        await pilot.pause()

        assert str(stage_lbl.render()) == "Muxing Episodes..."
        assert loading_ind.display is False
        assert progress_bar.display is True
        assert progress_bar.total == 12
        assert progress_bar.progress == 3
        assert "Muxing: 3/12 episodes" in str(detail_lbl.render())

        # 3. Done mode
        panel.update_progress(
            ProgressUpdate(stage="done", current=12, total=12, label="Finished")
        )
        await pilot.pause()

        assert str(stage_lbl.render()) == "Pipeline Complete! ✓"
        assert loading_ind.display is False
        assert progress_bar.display is True
        assert progress_bar.progress == 12
        assert "All episodes muxed" in str(detail_lbl.render())
