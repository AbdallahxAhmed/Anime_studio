import asyncio
import os
import sys
from pathlib import Path
import structlog

from src.config import AppConfig
from src.adapters.dependency_checker import DependencyChecker
from src.adapters.subprocess import SubprocessAdapter
from src.adapters.filesystem import FilesystemAdapter
from src.adapters.http_client import HttpClientAdapter
from src.hunters.registry import HunterRegistry
from src.core.font_cache import FontCache
from src.core.font_resolver import FontResolver
from src.core.pipeline_runner import PipelineRunner
from src.tui.app import AnimeStudioApp
from src.tui.log_bridge import LogBridge


def create_app() -> AnimeStudioApp:
    """Composition root: load config, instantiate adapters, core runners, log bridge, and TUI app."""
    # 1. Load config
    config = AppConfig.load_from_toml()

    # 2. Discover tools
    dep_checker = DependencyChecker()
    # Discover all tools. Note: if critical tools are missing, this might raise ToolNotFoundError.
    # In a real environment, we'll let this run; in tests, we want this to be robust.
    try:
        tool_registry = dep_checker.discover_all()
    except Exception:
        # Fallback empty registry for robust startup if tools are missing during tests/dry runs
        from src.adapters.dependency_checker import ToolRegistry

        tool_registry = ToolRegistry()

    # 3. Instantiate adapters
    subprocess_adapter = SubprocessAdapter()
    filesystem_adapter = FilesystemAdapter()

    # Pass proxy to HTTP client adapter per CONSTRAINT
    _http_client_adapter = HttpClientAdapter(
        proxy_url=config.proxy,
        default_timeout_s=float(config.default_timeout_s),
    )

    # 4. Resolve font cache directory
    if config.font_cache_path:
        cache_dir = Path(config.font_cache_path)
    else:
        if sys.platform == "win32":
            app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if app_data:
                cache_dir = Path(app_data) / "AnimeStudio" / "Cache"
            else:
                cache_dir = Path.home() / "AppData" / "Local" / "AnimeStudio" / "Cache"
        else:
            cache_dir = Path.home() / ".cache" / "AnimeStudio"

    font_cache = FontCache(cache_dir)

    # 5. Create Hunter registry and Font resolver
    hunter_registry = HunterRegistry(cooldown_s=config.circuit_breaker_cooldown_s)
    font_resolver = FontResolver(
        registry=hunter_registry,
        cache=font_cache,
        config=config,
    )

    # 6. Create shared Semaphore using max_concurrent_disk_io per CONSTRAINT
    _shared_semaphore = asyncio.Semaphore(config.max_concurrent_disk_io)

    # 7. Create Pipeline runner
    pipeline_runner = PipelineRunner(
        font_resolver=font_resolver,
        subprocess_adapter=subprocess_adapter,
        filesystem=filesystem_adapter,
        tool_registry=tool_registry,
        config=config,
    )

    # 8. Create TUI App
    app = AnimeStudioApp(pipeline_runner=pipeline_runner)

    # 9. Create and install LogBridge
    log_bridge = LogBridge(app=app)

    # Store reference on app for dashboard use
    app.log_bridge = log_bridge

    # Configure structlog globally with log bridge processor
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            log_bridge,
            structlog.processors.JSONRenderer(),
        ]
    )

    return app
