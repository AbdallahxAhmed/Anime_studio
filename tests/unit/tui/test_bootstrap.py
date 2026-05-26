from pathlib import Path
from unittest.mock import patch

from src.tui.bootstrap import create_app
from src.tui.app import AnimeStudioApp
from src.config import AppConfig


def test_create_app_constructs_everything():
    mock_config = AppConfig(
        proxy="http://localhost:8080",
        max_concurrent_disk_io=7,
        font_cache_path="D:\\dummy\\cache",
    )

    with (
        patch("src.config.AppConfig.load_from_toml", return_value=mock_config),
        patch("src.adapters.dependency_checker.DependencyChecker.discover_all"),
        patch(
            "src.core.font_cache.FontCache.__init__", return_value=None
        ) as mock_cache_init,
    ):
        app = create_app()

        # Check that it returns an AnimeStudioApp instance
        assert isinstance(app, AnimeStudioApp)

        # Verify app holds the pipeline runner
        assert app.pipeline_runner is not None

        # Verify pipeline runner dependencies are set
        runner = app.pipeline_runner
        assert runner.config == mock_config
        assert runner.font_resolver is not None
        assert runner.subprocess_adapter is not None
        assert runner.filesystem is not None
        assert runner.tool_registry is not None

        # Verify log bridge is installed on the app
        assert app.log_bridge is not None
        assert app.log_bridge.app == app

        # Verify font cache directory initialization was called with configured path
        mock_cache_init.assert_called_once_with(Path("D:\\dummy\\cache"))
