"""Non-media end-to-end Stop coverage for the Phase 8 cancellation contract."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from src.adapters.dependency_checker import ToolRegistry
from src.config import AppConfig
from src.core.font_resolver import FontResolver
from src.core.library_scanner import LibraryScanner
from src.core.pipeline_runner import PipelineRunner
from src.gui.log_bridge import GuiLogBridge
from src.gui.main_window import MainWindow
from src.hunters.registry import HunterRegistry
from src.hunters.sources.mkv_extract import MkvExtractHunter
from src.models.font import FontAsset, FontPayload
from src.models.pipeline import (
    LibraryScanOutput,
    LibraryScanResult,
    ShowStatus,
    ShowSummary,
)
from src.models.tool_result import ToolResult
from src.models.trash import TrashReceipt


@dataclass(frozen=True)
class _WindowConfig:
    """The small presentation configuration surface used by ``MainWindow``."""

    library_path: Path
    dry_run: bool = True


class _ControlledSubprocess:
    """Block only the scoped hunter identify call until the test releases it."""

    def __init__(self) -> None:
        self.identify_started = asyncio.Event()
        self.release_identify = asyncio.Event()
        self.identified_paths: list[Path] = []

    async def execute(
        self, args: Sequence[str], timeout: float | None = None
    ) -> ToolResult:
        del timeout
        assert args[0] == "mkvmerge"
        assert args[1] == "-J"
        self.identified_paths.append(Path(args[-1]).resolve())
        self.identify_started.set()
        await self.release_identify.wait()
        return ToolResult(
            tool_name="mkvmerge",
            success=True,
            exit_code=0,
            stdout=json.dumps({"attachments": []}),
            stderr="",
            duration_ms=0.0,
        )


class _NoWriteFontCache:
    """A real resolver boundary that proves Stop prevents cache persistence."""

    def __init__(self) -> None:
        self.store_calls = 0

    def lookup(self, font_name: str) -> FontAsset | None:
        del font_name
        return None

    def store(self, payload: FontPayload, layer_found: int) -> FontAsset:
        del payload, layer_found
        self.store_calls += 1
        raise AssertionError("font cache must not be written after Stop")


class _RecordingFilesystem:
    """Mocked side-effect boundary; every write is retained for assertions."""

    def __init__(self) -> None:
        self.written_paths: list[Path] = []
        self.replaced_paths: list[tuple[Path, Path]] = []
        self.trash_moves: list[Path] = []

    async def move_to_trash(self, source: Path, trash_receipt: TrashReceipt) -> None:
        del trash_receipt
        self.trash_moves.append(source)

    async def write_file_atomic(
        self, target: Path, content: str, encoding: str = "utf-8"
    ) -> None:
        del content, encoding
        self.written_paths.append(target)

    async def ensure_directory(self, path: Path) -> None:
        del path

    async def replace_file(self, source: Path, target: Path) -> None:
        self.replaced_paths.append((source, target))


class _NoopFontIngestion:
    async def ingest_directories(self, directories: list[Path], source: str) -> None:
        del directories, source


class _RecordingShowIndex:
    def __init__(self) -> None:
        self.status_updates: list[tuple[Path, ShowStatus]] = []

    async def update_status(self, path: Path, status: ShowStatus) -> None:
        self.status_updates.append((path, status))


def _pending_pipeline_or_hunter_tasks() -> list[asyncio.Task[object]]:
    """Return only pending tasks owned by the run under test."""

    current_task = asyncio.current_task()
    owned_tasks: list[asyncio.Task[object]] = []
    for task in asyncio.all_tasks():
        if task is current_task or task.done():
            continue
        qualified_name = getattr(task.get_coro(), "__qualname__", "")
        if "PipelineRunner" in qualified_name or "MkvExtractHunter" in qualified_name:
            owned_tasks.append(task)
    return owned_tasks


@pytest.mark.asyncio
async def test_main_window_stop_cancels_real_scoped_pipeline_without_artifacts(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop flows from the real GUI through scanner, runner, and scoped hunter.

    The fake library intentionally has two identically named MKVs.  The only
    subprocess boundary is held inside the real per-run hunter so the test can
    prove that Show B was never enumerated while the selected Show A run stops.
    """

    library_root = tmp_path / "Library"
    # The unrelated directory intentionally sorts first.  A mistaken global
    # discovery root would identify it before the selected show and fail the
    # assertion below before Stop is requested.
    show_a = library_root / "B Selected Show A"
    show_b = library_root / "A Unrelated Show B"
    show_a.mkdir(parents=True)
    show_b.mkdir()
    episode_a = show_a / "episode_01.mkv"
    episode_b = show_b / "episode_01.mkv"
    episode_a.touch()
    episode_b.touch()
    subtitle_a = show_a / "episode_01.ass"
    subtitle_a.write_text(
        "[Script Info]\n"
        "Title: Phase 8 fake media\n"
        "ScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize\n"
        "Style: Default,TestTTF,20\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Stop test\n",
        encoding="utf-8",
    )

    # Never permit the optional synchronizers to reach a locally installed binary.
    monkeypatch.setattr("src.core.pipeline_runner.shutil.which", lambda _name: None)

    controlled_subprocess = _ControlledSubprocess()
    base_hunter = MkvExtractHunter(controlled_subprocess)
    registry = HunterRegistry()
    registry.register(base_hunter)
    no_write_cache = _NoWriteFontCache()
    runner_config = AppConfig(library_path=library_root, max_concurrent_disk_io=1)
    resolver = FontResolver(registry, no_write_cache, runner_config)
    filesystem = _RecordingFilesystem()
    scanner = LibraryScanner()
    runner = PipelineRunner(
        font_resolver=resolver,
        subprocess_adapter=controlled_subprocess,
        filesystem=filesystem,
        tool_registry=ToolRegistry(),
        config=runner_config,
        font_ingestion_service=_NoopFontIngestion(),
        disk_semaphore=asyncio.Semaphore(1),
        library_scanner=scanner,
    )

    show_index = _RecordingShowIndex()
    window = MainWindow(
        pipeline_runner=runner,
        log_bridge=GuiLogBridge(),
        config=_WindowConfig(library_root),
        font_ingestion_service=_NoopFontIngestion(),
        show_index_manager=show_index,
    )
    qtbot.addWidget(window)
    window.show()

    resolved_show_a = show_a.resolve()
    resolved_episode_a = episode_a.resolve()
    window._sidebar.add_show(
        ShowSummary(
            name="Show A",
            path=resolved_show_a,
            status=ShowStatus.READY,
            episode_count=1,
            processed_count=0,
            subtitle_text="1 ready",
        )
    )
    window._display_scan_result(
        "Show A",
        resolved_show_a,
        LibraryScanOutput(
            episodes=[
                LibraryScanResult(
                    episode_path=resolved_episode_a,
                    subtitle_path=subtitle_a.resolve(),
                    anime_title="Show A",
                )
            ],
            font_directories=[],
        ),
    )
    assert window.run_button.isEnabled()

    # Call the coroutine behind qasync's slot wrapper, then use the real Qt
    # button click to exercise MainWindow's Stop handler.
    run_task = asyncio.create_task(window._on_run_click.__wrapped__(window))
    await controlled_subprocess.identify_started.wait()

    assert window._pipeline_running
    assert window.stop_button.isVisible()
    assert controlled_subprocess.identified_paths == [resolved_episode_a]
    qtbot.mouseClick(window.stop_button, Qt.MouseButton.LeftButton)
    assert window.stop_button.text() == "Stopping..."
    assert not window.stop_button.isEnabled()

    # A user stop lets the already-running owned binary boundary finish; the
    # hunter must then discard its result and propagate PipelineStoppedError.
    controlled_subprocess.release_identify.set()
    await run_task

    assert controlled_subprocess.identified_paths == [resolved_episode_a]
    assert episode_b.resolve() not in controlled_subprocess.identified_paths
    assert base_hunter.scope.discovery_root is None
    assert no_write_cache.store_calls == 0
    assert filesystem.written_paths == []
    assert filesystem.replaced_paths == []
    assert filesystem.trash_moves == []
    assert not (library_root / "_AnimeStudio_Report.md").exists()
    assert list(show_a.glob("*.tmp.*")) == []

    assert window.progress_panel.status_label.text() == "Pipeline stopped by user."
    assert "success" not in window.progress_panel.status_label.text().casefold()
    assert window._sidebar.get_show_status(resolved_show_a) == ShowStatus.READY
    assert show_index.status_updates == [
        (resolved_show_a, ShowStatus.PROCESSING),
        (resolved_show_a, ShowStatus.READY),
    ]
    assert not window._pipeline_running
    assert window._stop_event is None
    assert not window.stop_button.isVisible()
    assert window.run_button.isEnabled()
    assert window.undo_button.isEnabled()
    assert window.settings_btn.isEnabled()
    assert run_task.done()
    assert _pending_pipeline_or_hunter_tasks() == []
