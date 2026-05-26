import pytest
from unittest.mock import AsyncMock, MagicMock
from src.tui.app import AnimeStudioApp
from src.core.pipeline_runner import PipelineRunner
from src.models.report import PipelineReport


@pytest.fixture
def mock_pipeline_runner():
    runner = MagicMock(spec=PipelineRunner)
    runner.run = AsyncMock(
        return_value=PipelineReport(
            run_timestamp=MagicMock(),
            duration_ms=42.0,
            anime_title="Mocked Anime",
            episodes=[],
            total_fonts_found=0,
            genuine_misses=[],
        )
    )
    return runner


@pytest.mark.asyncio
async def test_app_launches_dashboard(mock_pipeline_runner):
    app = AnimeStudioApp(pipeline_runner=mock_pipeline_runner)
    async with app.run_test():
        # Check DashboardScreen is mounted
        from src.tui.screens.dashboard import DashboardScreen

        assert app.query_one(DashboardScreen) is not None

        # Verify inputs and buttons exist
        path_input = app.screen.query_one("#library-path")
        run_button = app.screen.query_one("#run-pipeline")
        dry_run_cb = app.screen.query_one("#dry-run")

        assert path_input is not None
        assert run_button is not None
        assert dry_run_cb is not None
        assert run_button.disabled is True


@pytest.mark.asyncio
async def test_path_validation_enables_button(mock_pipeline_runner):
    app = AnimeStudioApp(pipeline_runner=mock_pipeline_runner)
    async with app.run_test() as pilot:
        run_button = app.screen.query_one("#run-pipeline")
        assert run_button.disabled is True

        # Input valid path
        path_input = app.screen.query_one("#library-path")
        path_input.value = "D:\\Anime"

        # Wait for reactive watch/event handling
        await pilot.pause()
        assert run_button.disabled is False

        # Set to empty path, should disable again
        path_input.value = ""
        await pilot.pause()
        assert run_button.disabled is True


@pytest.mark.asyncio
async def test_fatal_pipeline_error_shows_modal(mock_pipeline_runner):
    from src.tui.messages import PipelineError
    from src.errors import ToolNotFoundError
    from src.tui.widgets.error_modal import ErrorModal
    from src.tui.screens.dashboard import DashboardScreen

    app = AnimeStudioApp(pipeline_runner=mock_pipeline_runner)
    async with app.run_test() as pilot:
        dashboard = app.query_one(DashboardScreen)
        err = ToolNotFoundError("mkvmerge not found")
        dashboard.post_message(PipelineError(error=err, fatal=True))
        await pilot.pause()

        assert isinstance(app.screen, ErrorModal)
        assert "Critical Dependency Missing" in app.screen.error_title
        assert "mkvmerge not found" in app.screen.error_message

        await pilot.click("#dismiss-button")
        await pilot.pause()
        assert not isinstance(app.screen, ErrorModal)


@pytest.mark.asyncio
async def test_non_fatal_pipeline_error_shows_toast(mock_pipeline_runner):
    from unittest.mock import patch
    from src.tui.messages import PipelineError
    from src.errors import FontMatchError
    from src.tui.screens.dashboard import DashboardScreen

    app = AnimeStudioApp(pipeline_runner=mock_pipeline_runner)
    async with app.run_test() as pilot:
        dashboard = app.query_one(DashboardScreen)
        err = FontMatchError("Could not resolve Arial")

        with patch.object(app, "notify") as mock_notify:
            dashboard.post_message(PipelineError(error=err, fatal=True))
            await pilot.pause()
            mock_notify.assert_called_once()
            args, kwargs = mock_notify.call_args
            assert "Could not resolve Arial" in args[0]
            assert kwargs.get("severity") == "error"


@pytest.mark.asyncio
async def test_generic_pipeline_error_shows_unhandled_modal(mock_pipeline_runner):
    from src.tui.messages import PipelineError
    from src.tui.widgets.error_modal import ErrorModal
    from src.tui.screens.dashboard import DashboardScreen

    app = AnimeStudioApp(pipeline_runner=mock_pipeline_runner)
    async with app.run_test() as pilot:
        dashboard = app.query_one(DashboardScreen)
        err = ValueError("Something weird happened")
        dashboard.post_message(PipelineError(error=err, fatal=True))
        await pilot.pause()

        assert isinstance(app.screen, ErrorModal)
        assert "Fatal Unhandled Exception" in app.screen.error_title
        assert "Something weird happened" in app.screen.error_message


@pytest.mark.asyncio
async def test_checkbox_toggle_sets_dry_run(mock_pipeline_runner):
    from src.tui.screens.dashboard import DashboardScreen

    app = AnimeStudioApp(pipeline_runner=mock_pipeline_runner)
    async with app.run_test() as pilot:
        dashboard = app.query_one(DashboardScreen)
        path_input = dashboard.query_one("#library-path")
        path_input.value = "D:\\Anime"

        dry_run_cb = dashboard.query_one("#dry-run")
        dry_run_cb.value = True

        await pilot.pause()
        run_btn = dashboard.query_one("#run-pipeline")
        assert not run_btn.disabled

        run_btn.press()
        await pilot.pause()

        import asyncio

        for _ in range(10):
            if mock_pipeline_runner.run.called:
                break
            await asyncio.sleep(0.05)

        mock_pipeline_runner.run.assert_called_once()
        args, _ = mock_pipeline_runner.run.call_args
        assert args[0].dry_run is True
