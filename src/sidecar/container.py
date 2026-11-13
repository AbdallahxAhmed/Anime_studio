"""Composition root for the desktop backend: adapters → core services, no Qt.

Mirrors ``src/gui/bootstrap.py`` but never raises when a tool is missing:
the desktop app shows a setup screen instead of crashing.
"""

from __future__ import annotations

import asyncio
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from src.adapters.dependency_checker import (
    DEFAULT_SPECS,
    BinaryClassification,
    DependencyChecker,
    ResolvedTool,
    ToolRegistry,
)
from src.adapters.filesystem import FilesystemAdapter
from src.adapters.font_face_reader import FontFaceReaderAdapter
from src.adapters.mkvextract import MkvextractAdapter
from src.adapters.mkvmerge import MkvmergeAdapter
from src.adapters.subprocess import SubprocessAdapter
from src.config import AppConfig
from src.core.checkpoint_manager import CheckpointManager
from src.core.font_cache import FontCache
from src.core.font_ingestion import FontIngestionService
from src.core.font_resolver import FontResolver
from src.core.library_scanner import LibraryScanner
from src.core.pipeline_runner import PipelineRunner
from src.core.renderability_service import RenderabilityService
from src.core.undo_service import UndoService
from src.hunters.registry import HunterRegistry
from src.hunters.sources.arabic_fonts import ArabicFontsHunter
from src.hunters.sources.befonts import BeFontsHunter
from src.hunters.sources.dafont import DaFontHunter
from src.hunters.sources.fontspace import FontSpaceHunter
from src.hunters.sources.fontsquirrel import FontSquirrelHunter
from src.hunters.sources.google_fonts import GoogleFontsHunter
from src.hunters.sources.mkv_extract import MkvExtractHunter
from src.hunters.sources.search_engine import SearchEngineHunter
from src.hunters.sources.sibling_font import SiblingFontHunter
from src.hunters.system_font_hunter import SystemFontHunter

_LEGACY_CACHE = Path("D:/Entertainment/.anime_studio/font_cache")


def data_dir() -> Path:
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        return base / "AnimeStudio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AnimeStudio"
    return Path.home() / ".config" / "AnimeStudio"


def config_path() -> Path:
    return data_dir() / "config.toml"


def _linux_distro() -> str:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return ""
    ids: list[str] = []
    for line in text.splitlines():
        if line.startswith(("ID=", "ID_LIKE=")):
            ids.extend(line.split("=", 1)[1].strip().strip('"').split())
    return " ".join(ids)


def install_hint(tool: str) -> str:
    """One install command for this OS (MKVToolNix provides both mkv tools)."""
    package = "mkvtoolnix" if tool.startswith("mkv") else tool
    if sys.platform == "win32":
        return f"scoop install {package}"
    if sys.platform == "darwin":
        return f"brew install {package}"
    distro = _linux_distro()
    if "arch" in distro:
        name = "mkvtoolnix-cli" if package == "mkvtoolnix" else package
        return f"sudo pacman -S {name}"
    if "fedora" in distro or "rhel" in distro:
        return f"sudo dnf install {package}"
    if "debian" in distro or "ubuntu" in distro:
        return f"sudo apt install {package}"
    return f"Install {package} with your package manager"


@dataclass
class ToolStatus:
    name: str
    required: bool
    found: bool
    path: str
    hint: str


def discover_tools() -> tuple[ToolRegistry, list[ToolStatus]]:
    checker = DependencyChecker()
    registry = ToolRegistry()
    statuses: list[ToolStatus] = []
    for spec in DEFAULT_SPECS:
        resolved = checker.discover_one(spec)
        required = spec.classification == BinaryClassification.CRITICAL
        registry.register(
            ResolvedTool(
                name=spec.name,
                path=resolved or Path(""),
                classification=spec.classification,
                is_available=resolved is not None,
            )
        )
        statuses.append(
            ToolStatus(
                name=spec.name,
                required=required,
                found=resolved is not None,
                path=str(resolved) if resolved else "",
                hint=install_hint(spec.name),
            )
        )
    return registry, statuses


@dataclass
class Services:
    config: AppConfig
    data_dir: Path
    tools: list[ToolStatus]
    runner: PipelineRunner
    scanner: LibraryScanner
    undo: UndoService
    checkpoints: CheckpointManager
    font_ingestion: FontIngestionService

    @property
    def missing_required_tools(self) -> list[str]:
        return [t.name for t in self.tools if t.required and not t.found]

    @property
    def platform_name(self) -> str:
        return f"{platform.system()} {platform.release()}"


def build_services(config: AppConfig | None = None) -> Services:
    config = config or AppConfig.load_from_toml(config_path())
    root = data_dir()
    registry, statuses = discover_tools()

    subprocess_adapter = SubprocessAdapter(tool_registry=registry)
    filesystem = FilesystemAdapter()

    cache_dir = config.font_cache_path or (
        _LEGACY_CACHE if _LEGACY_CACHE.exists() else root / "font_cache"
    )
    font_cache = FontCache(cache_dir=cache_dir)

    hunters = HunterRegistry(cooldown_s=config.circuit_breaker_cooldown_s)
    hunters.register(MkvExtractHunter(subprocess_port=subprocess_adapter))
    hunters.register(SiblingFontHunter())
    hunters.register(SystemFontHunter())
    for network_hunter in (
        GoogleFontsHunter,
        FontSquirrelHunter,
        DaFontHunter,
        FontSpaceHunter,
        BeFontsHunter,
        ArabicFontsHunter,
        SearchEngineHunter,
    ):
        hunters.register(network_hunter(proxy=config.proxy))

    disk_semaphore = asyncio.Semaphore(config.max_concurrent_disk_io)
    font_ingestion = FontIngestionService(
        cache=font_cache, disk_semaphore=disk_semaphore
    )
    mkvmerge = MkvmergeAdapter(subprocess_port=subprocess_adapter)
    scanner = LibraryScanner(mkvmerge=mkvmerge)
    runner = PipelineRunner(
        font_resolver=FontResolver(registry=hunters, cache=font_cache, config=config),
        subprocess_adapter=subprocess_adapter,
        filesystem=filesystem,
        tool_registry=registry,
        config=config,
        font_ingestion_service=font_ingestion,
        disk_semaphore=disk_semaphore,
        library_scanner=scanner,
        renderability_service=RenderabilityService(FontFaceReaderAdapter()),
        mkvextract_adapter=MkvextractAdapter(subprocess_port=subprocess_adapter),
        mkvmerge=mkvmerge,
    )
    return Services(
        config=config,
        data_dir=root,
        tools=statuses,
        runner=runner,
        scanner=scanner,
        undo=UndoService(
            data_dir=root,
            filesystem_port=filesystem,
            max_run_history=config.max_run_history,
        ),
        checkpoints=CheckpointManager(root),
        font_ingestion=font_ingestion,
    )
