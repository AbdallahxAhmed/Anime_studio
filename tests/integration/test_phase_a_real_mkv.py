"""Phase A exit test on real MKV files (needs ffmpeg and MKVToolNix).

Run → Arabic track tagged and default, other subtitles kept → undo restores
a byte-identical original and the external subtitle.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.adapters.dependency_checker import DependencyChecker
from src.adapters.filesystem import FilesystemAdapter
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
from src.core.undo_service import UndoService
from src.hunters.registry import HunterRegistry
from src.models.pipeline import PipelineConfig

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("mkvmerge")),
        reason="needs ffmpeg and mkvmerge",
    ),
]

ASS_TEMPLATE = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.50,Default,,0,0,0,,{text}
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identify(path: Path) -> dict:  # type: ignore[type-arg]
    out = subprocess.run(
        ["mkvmerge", "-J", str(path)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)  # type: ignore[no-any-return]


def _make_episode(folder: Path) -> Path:
    english = folder / "eng.ass"
    english.write_text(ASS_TEMPLATE.format(text="Hello"), encoding="utf-8")
    episode = folder / "Show - 01.mkv"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=12:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-i", str(english),
            "-map", "0", "-map", "1", "-map", "2",
            "-c:v", "mpeg4", "-c:a", "aac", "-c:s", "ass",
            "-metadata:s:s:0", "language=eng", "-disposition:s:0", "default",
            str(episode),
        ],
        check=True,
    )  # fmt: skip
    english.unlink()
    return episode


def _runner(tmp_path: Path) -> tuple[PipelineRunner, UndoService, CheckpointManager]:
    config = AppConfig(font_cache_path=tmp_path / "cache")
    registry = DependencyChecker().discover_all()
    subprocess_adapter = SubprocessAdapter(tool_registry=registry)
    filesystem = FilesystemAdapter()
    cache = FontCache(cache_dir=tmp_path / "cache")
    semaphore = asyncio.Semaphore(2)
    mkvmerge = MkvmergeAdapter(subprocess_port=subprocess_adapter)
    runner = PipelineRunner(
        font_resolver=FontResolver(HunterRegistry(), cache, config),
        subprocess_adapter=subprocess_adapter,
        filesystem=filesystem,
        tool_registry=registry,
        config=config,
        font_ingestion_service=FontIngestionService(cache, semaphore),
        disk_semaphore=semaphore,
        library_scanner=LibraryScanner(mkvmerge=mkvmerge),
        mkvextract_adapter=MkvextractAdapter(subprocess_port=subprocess_adapter),
        mkvmerge=mkvmerge,
    )
    data = tmp_path / "data"
    return runner, UndoService(data, filesystem), CheckpointManager(data)


@pytest.mark.anyio
async def test_apply_then_undo_on_real_mkv(tmp_path: Path) -> None:
    library = tmp_path / "library"
    show = library / "Show"
    show.mkdir(parents=True)
    episode = _make_episode(show)
    subtitle = show / "Show - 01.ass"
    # Arabic subtitles are often saved as Windows-1256, not UTF-8.
    subtitle.write_bytes(ASS_TEMPLATE.format(text="مرحبا بالعالم").encode("cp1256"))
    original_hash = _sha(episode)
    subtitle_hash = _sha(subtitle)

    runner, undo, checkpoints = _runner(tmp_path)
    report = await runner.run(
        PipelineConfig(library_path=library, discovery_root=show),
        checkpoint_manager=checkpoints,
        undo_service=undo,
    )

    assert [e.status.value for e in report.episodes] == ["partial"]  # Arial missing
    info = _identify(episode)
    subs = [t for t in info["tracks"] if t["type"] == "subtitles"]
    assert [t["properties"]["language"] for t in subs] == ["eng", "ara"]
    assert [t["properties"]["default_track"] for t in subs] == [False, True]
    assert subs[1]["properties"]["track_name"] == "Arabic"
    assert not subtitle.exists()
    extracted = tmp_path / "check.ass"
    subprocess.run(
        ["mkvextract", str(episode), "tracks", f"{subs[1]['id']}:{extracted}"],
        capture_output=True,
        check=True,
    )
    assert "مرحبا بالعالم" in extracted.read_text(encoding="utf-8-sig")
    assert list(show.glob("*.tmp.*")) == []  # no temp files left behind
    assert await checkpoints.load() is None  # cleared after a clean run

    manifest = (await undo.list_runs())[0]
    result = await undo.undo_episode(manifest, episode)

    assert result.restored == 1
    assert _sha(episode) == original_hash
    assert _sha(subtitle) == subtitle_hash
    backups = show / ".anime_studio_trash"
    assert len(list(backups.glob("UNDONE-*"))) == 1
