import importlib
import sys
from pathlib import Path
from typing import Any
from PySide6.QtWidgets import QApplication


def map_pipeline_report(report: Any, library_path: Path, dry_run: bool) -> Any:
    """Map PipelineReport domain model to PipelineRunResult presentation model.

    Imports models and presentation types dynamically to avoid boundary leakage.
    """
    gui_messages = importlib.import_module("src.gui.messages")
    EpisodeResult = gui_messages.EpisodeResult
    GuiStatus = gui_messages.EpisodeStatus
    PipelineRunResult = gui_messages.PipelineRunResult

    model_report = importlib.import_module("src.models.report")
    ModelStatus = model_report.EpisodeStatus

    episode_results = []
    for ep in report.episodes:
        if ep.status == ModelStatus.COMPLETE:
            status = GuiStatus.COMPLETE
        elif ep.status == ModelStatus.PARTIAL:
            status = GuiStatus.PARTIAL
        elif ep.status == ModelStatus.FAILED:
            status = GuiStatus.FAILED
        else:
            status = GuiStatus.SKIPPED

        fonts_found = (
            ep.mux_result.fonts_attached
            if (ep.mux_result and ep.mux_result.success)
            else 0
        )
        fonts_missing = len(ep.missing_fonts)

        error_summary = None
        if ep.applied_rules:
            error_summary = "; ".join(ep.applied_rules)
        elif ep.status == ModelStatus.FAILED:
            error_summary = "Muxing or timing pipeline failed"
        elif ep.status == ModelStatus.SKIPPED:
            error_summary = "Skipped (no matching subtitle file)"

        episode_results.append(
            EpisodeResult(
                name=ep.episode_path.name,
                episode_path=ep.episode_path,
                status=status,
                fonts_found=fonts_found,
                fonts_missing=fonts_missing,
                error_summary=error_summary,
            )
        )

    return PipelineRunResult(
        episodes=episode_results,
        total_duration_seconds=report.duration_ms / 1000.0,
        report_path=str(library_path / "_AnimeStudio_Report.md"),
        total_fonts_found=report.total_fonts_found,
        total_fonts_missing=len(report.genuine_misses),
        dry_run=dry_run,
    )


def bootstrap_app(app: QApplication) -> Any:
    """Wire adapters -> core services -> MainWindow and configure logging.

    All non-GUI modules (core, adapters, models, hunters) are imported dynamically
    at runtime to maintain strict Hexagonal Architecture boundaries and prevent
    static coupling/leakage.
    """
    # 1. Load config
    config_mod = importlib.import_module("src.config")
    AppConfig = config_mod.AppConfig
    config = AppConfig.load_from_toml()

    # Resolve font cache path based on constitution
    cache_dir = config.font_cache_path
    if not cache_dir:
        d_path = Path("D:/Entertainment/.anime_studio/font_cache")
        if d_path.exists():
            cache_dir = d_path
        else:
            if sys.platform == "win32":
                cache_dir = Path("D:/Entertainment/.anime_studio/font_cache")
            else:
                cache_dir = Path.home() / ".anime_studio" / "font_cache"

    # 2. Resolve dependencies first
    adapters_dep = importlib.import_module("src.adapters.dependency_checker")
    DependencyChecker = adapters_dep.DependencyChecker
    dependency_checker = DependencyChecker()
    tool_registry = dependency_checker.discover_all()

    # 3. Create adapters dynamically
    adapters_sub = importlib.import_module("src.adapters.subprocess")
    SubprocessAdapter = adapters_sub.SubprocessAdapter
    subprocess_adapter = SubprocessAdapter(tool_registry=tool_registry)

    adapters_fs = importlib.import_module("src.adapters.filesystem")
    FilesystemAdapter = adapters_fs.FilesystemAdapter
    filesystem_adapter = FilesystemAdapter()

    # 3. Create core services dynamically
    core_cache = importlib.import_module("src.core.font_cache")
    FontCache = core_cache.FontCache
    font_cache = FontCache(cache_dir=cache_dir)

    # Dynamically load HunterRegistry to enforce strict hexagonal layer boundaries
    registry_mod = importlib.import_module("src.hunters.registry")
    HunterRegistry = registry_mod.HunterRegistry
    hunter_registry = HunterRegistry(cooldown_s=config.circuit_breaker_cooldown_s)

    # Dynamically load and register all hunters in priority order
    # Layer 1: MkvExtractHunter
    mkv_extract_mod = importlib.import_module("src.hunters.sources.mkv_extract")
    MkvExtractHunter = mkv_extract_mod.MkvExtractHunter
    hunter_registry.register(
        MkvExtractHunter(
            subprocess_port=subprocess_adapter, library_path=config.library_path
        )
    )

    # Layer 2: SiblingFontHunter
    sibling_font_mod = importlib.import_module("src.hunters.sources.sibling_font")
    SiblingFontHunter = sibling_font_mod.SiblingFontHunter
    hunter_registry.register(SiblingFontHunter())

    # Layer 3: SystemFontHunter
    system_font_mod = importlib.import_module("src.hunters.system_font_hunter")
    SystemFontHunter = system_font_mod.SystemFontHunter
    hunter_registry.register(SystemFontHunter())

    # Layer 4A: GoogleFontsHunter
    google_fonts_mod = importlib.import_module("src.hunters.sources.google_fonts")
    GoogleFontsHunter = google_fonts_mod.GoogleFontsHunter
    hunter_registry.register(GoogleFontsHunter(proxy=config.proxy))

    # Layer 4B: FontSquirrelHunter
    fontsquirrel_mod = importlib.import_module("src.hunters.sources.fontsquirrel")
    FontSquirrelHunter = fontsquirrel_mod.FontSquirrelHunter
    hunter_registry.register(FontSquirrelHunter(proxy=config.proxy))

    # Layer 4C: DaFontHunter
    dafont_mod = importlib.import_module("src.hunters.sources.dafont")
    DaFontHunter = dafont_mod.DaFontHunter
    hunter_registry.register(DaFontHunter(proxy=config.proxy))

    # Layer 4D: FontSpaceHunter
    fontspace_mod = importlib.import_module("src.hunters.sources.fontspace")
    FontSpaceHunter = fontspace_mod.FontSpaceHunter
    hunter_registry.register(FontSpaceHunter(proxy=config.proxy))

    # Layer 4E: BeFontsHunter
    befonts_mod = importlib.import_module("src.hunters.sources.befonts")
    BeFontsHunter = befonts_mod.BeFontsHunter
    hunter_registry.register(BeFontsHunter(proxy=config.proxy))

    # Layer 4F: ArabicFontsHunter
    arabic_fonts_mod = importlib.import_module("src.hunters.sources.arabic_fonts")
    ArabicFontsHunter = arabic_fonts_mod.ArabicFontsHunter
    hunter_registry.register(ArabicFontsHunter(proxy=config.proxy))

    # Layer 5: SearchEngineHunter
    search_engine_mod = importlib.import_module("src.hunters.sources.search_engine")
    SearchEngineHunter = search_engine_mod.SearchEngineHunter
    hunter_registry.register(SearchEngineHunter(proxy=config.proxy))

    core_resolver = importlib.import_module("src.core.font_resolver")
    FontResolver = core_resolver.FontResolver
    font_resolver = FontResolver(
        registry=hunter_registry,
        cache=font_cache,
        config=config,
    )

    import asyncio

    disk_semaphore = asyncio.Semaphore(config.max_concurrent_disk_io)

    core_ingestion = importlib.import_module("src.core.font_ingestion")
    FontIngestionService = core_ingestion.FontIngestionService
    font_ingestion_service = FontIngestionService(
        cache=font_cache, disk_semaphore=disk_semaphore
    )

    # Create MkvmergeAdapter and LibraryScanner for embedded sub detection
    adapters_mkvmerge = importlib.import_module("src.adapters.mkvmerge")
    MkvmergeAdapter = adapters_mkvmerge.MkvmergeAdapter
    mkvmerge_adapter = MkvmergeAdapter(subprocess_port=subprocess_adapter)

    core_scanner = importlib.import_module("src.core.library_scanner")
    LibraryScanner = core_scanner.LibraryScanner
    library_scanner = LibraryScanner(mkvmerge=mkvmerge_adapter)

    core_runner = importlib.import_module("src.core.pipeline_runner")
    PipelineRunner = core_runner.PipelineRunner
    pipeline_runner = PipelineRunner(
        font_resolver=font_resolver,
        subprocess_adapter=subprocess_adapter,
        filesystem=filesystem_adapter,
        tool_registry=tool_registry,
        config=config,
        font_ingestion_service=font_ingestion_service,
        disk_semaphore=disk_semaphore,
        library_scanner=library_scanner,
    )

    # 4. Create log bridge
    log_bridge_mod = importlib.import_module("src.gui.log_bridge")
    GuiLogBridge = log_bridge_mod.GuiLogBridge
    log_bridge = GuiLogBridge()

    # Configure structlog
    structlog = importlib.import_module("structlog")
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        log_bridge,
        structlog.processors.JSONRenderer(),
    ]
    structlog.configure(processors=processors)

    # 5. Create MainWindow
    core_checkpoint = importlib.import_module("src.core.checkpoint_manager")
    CheckpointManager = core_checkpoint.CheckpointManager

    import os

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            data_dir = Path(app_data) / "AnimeStudio"
        else:
            data_dir = Path.home() / "AppData" / "Roaming" / "AnimeStudio"
    else:
        data_dir = Path.home() / ".config" / "AnimeStudio"

    checkpoint_manager = CheckpointManager(data_dir)

    core_undo = importlib.import_module("src.core.undo_service")
    UndoService = core_undo.UndoService
    undo_service = UndoService(
        data_dir=data_dir,
        filesystem_port=filesystem_adapter,
        max_run_history=config.max_run_history,
    )

    core_show_index = importlib.import_module("src.core.show_index")
    ShowIndexManager = core_show_index.ShowIndexManager
    show_index_manager = ShowIndexManager(
        config.library_path if config.library_path else data_dir
    )

    main_window_mod = importlib.import_module("src.gui.main_window")
    MainWindow = main_window_mod.MainWindow
    window = MainWindow(
        pipeline_runner=pipeline_runner,
        log_bridge=log_bridge,
        config=config,
        font_ingestion_service=font_ingestion_service,
        show_index_manager=show_index_manager,
        checkpoint_manager=checkpoint_manager,
        undo_service=undo_service,
    )

    import asyncio

    asyncio.ensure_future(window._on_startup())

    return window
