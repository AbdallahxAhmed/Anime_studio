"""Phase A safety fixes: undo swap, verified swap, unique backups, track flags."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.filesystem import FilesystemAdapter
from src.adapters.mkvmerge import MkvmergeAdapter
from src.config import AppConfig
from src.core.checkpoint_manager import CheckpointManager
from src.core.font_ingestion import FontIngestionService
from src.core.font_resolver import FontResolver
from src.core.library_scanner import LibraryScanner
from src.core.mux_planner import track_name_for
from src.core.mux_verifier import expected_subtitle_count, verify_mux_output
from src.core.pipeline_runner import PipelineRunner
from src.core.subtitle_repair import decode_subtitle_bytes
from src.core.undo_service import UndoService
from src.adapters.dependency_checker import ToolRegistry
from src.models.mux import MuxJob
from src.models.pipeline import LibraryScanOutput, LibraryScanResult, PipelineConfig
from src.models.report import EpisodeStatus
from src.models.run_manifest import EpisodeProcessed, PipelineCheckpoint, RunManifest
from src.models.tool_result import ToolResult
from src.models.trash import TrashReceipt
from src.ports.subprocess import SubprocessPort

NOW = datetime(2026, 11, 13, 21, 15, 7, tzinfo=timezone.utc)


def _identify(
    subs: list[dict[str, Any]],
    attachments: int = 0,
    duration: int = 2_000_000_000,
) -> dict[str, Any]:
    tracks: list[dict[str, Any]] = [
        {"id": 0, "type": "video", "properties": {}},
        {"id": 1, "type": "audio", "properties": {}},
    ]
    for index, sub in enumerate(subs, start=2):
        tracks.append({"id": index, "type": "subtitles", "properties": sub})
    return {
        "container": {"properties": {"duration": duration}},
        "tracks": tracks,
        "attachments": [{"id": i} for i in range(attachments)],
    }


def _job(**overrides: Any) -> MuxJob:
    values: dict[str, Any] = {
        "episode_path": Path("/anime/ep1.mkv"),
        "subtitle_path": Path("/anime/ep1.tmp.ass"),
        "fonts": [],
        "output_path": Path("/anime/ep1.tmp.mkv"),
        "subtitle_language": "ara",
        "subtitle_track_name": "Arabic",
        "make_default": True,
    }
    values.update(overrides)
    return MuxJob(**values)


# --- C1 / C2: undo swaps the processed file aside and restores side files ---


@pytest.mark.anyio
async def test_undo_restores_original_after_a_real_run(tmp_path: Path) -> None:
    show = tmp_path / "Show"
    backups = show / ".anime_studio_trash"
    backups.mkdir(parents=True)
    episode = show / "Show - 01.mkv"
    subtitle = show / "Show - 01.ass"
    episode_backup = backups / "EXP-2026-12-13-211507-Show - 01.mkv"
    subtitle_backup = backups / "EXP-2026-12-13-211507-Show - 01.ass"
    episode_backup.write_text("ORIGINAL")
    subtitle_backup.write_text("SUBTITLE")
    episode.write_text("MUXED")  # state after a successful run

    service = UndoService(tmp_path / "data", FilesystemAdapter())
    manifest = RunManifest(
        run_id="r1",
        timestamp=NOW.isoformat(),
        library_path=tmp_path,
        episodes_processed=(
            EpisodeProcessed(
                episode_path=episode,
                trash_receipt_path=episode_backup,
                show_name="Show",
                extra_restores=((subtitle, subtitle_backup),),
            ),
        ),
    )
    await service.save_manifest(manifest)

    loaded = (await service.list_runs())[0]
    assert loaded.episodes_processed[0].extra_restores == (
        (subtitle.as_posix(), subtitle_backup.as_posix()),
    )

    result = await service.undo_episode(loaded, episode)

    assert result.restored == 1
    assert episode.read_text() == "ORIGINAL"
    assert subtitle.read_text() == "SUBTITLE"
    aside = list(backups.glob("UNDONE-*"))
    assert len(aside) == 1 and aside[0].read_text() == "MUXED"
    # The record is cleared so a second undo cannot touch the file again.
    reloaded = (await service.list_runs())[0]
    assert reloaded.episodes_processed[0].trash_receipt_path is None


# --- C7: backups are unique and never overwritten ---


def test_backup_names_carry_the_run_tag() -> None:
    receipt = _job().plan_trash_disposal(NOW, 30, "211507")
    assert receipt.trash_path.name == "EXP-2026-12-13-211507-ep1.mkv"


@pytest.mark.anyio
async def test_move_to_trash_refuses_to_overwrite_a_backup(tmp_path: Path) -> None:
    source = tmp_path / "ep.mkv"
    source.write_text("NEW")
    backup = tmp_path / ".anime_studio_trash" / "EXP-ep.mkv"
    backup.parent.mkdir()
    backup.write_text("ORIGINAL")
    receipt = TrashReceipt(
        original_path=source,
        trash_path=backup,
        deletion_time=NOW,
        expiration_time=NOW,
    )

    with pytest.raises(FileExistsError):
        await FilesystemAdapter().move_to_trash(source, receipt)

    assert backup.read_text() == "ORIGINAL"
    assert source.read_text() == "NEW"


# --- M1: the new track is tagged, named and made default ---


@pytest.mark.anyio
async def test_mkvmerge_tags_new_track_and_clears_old_defaults() -> None:
    subprocess = MagicMock(spec=SubprocessPort)
    subprocess.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="mkvmerge",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
        )
    )
    job = _job(existing_subtitle_track_ids=[2, 3])

    await MkvmergeAdapter(subprocess).mux(job)

    args = subprocess.execute.await_args.args[0]
    episode_at = args.index(str(job.episode_path))
    subtitle_at = args.index(str(job.subtitle_path))
    before_episode = args[:episode_at]
    between = args[episode_at:subtitle_at]
    assert ["--default-track-flag", "2:no"] == before_episode[3:5]
    assert ["--default-track-flag", "3:no"] == before_episode[5:7]
    assert "--language" in between and "0:ara" in between
    assert "--track-name" in between and "0:Arabic" in between
    assert between[-2:] == ["--default-track-flag", "0:yes"]


@pytest.mark.anyio
async def test_mkvmerge_replaces_only_the_selected_embedded_track() -> None:
    subprocess = MagicMock(spec=SubprocessPort)
    subprocess.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="mkvmerge",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
        )
    )
    job = _job(replace_embedded_subtitles=True, replaced_track_id=3)

    await MkvmergeAdapter(subprocess).mux(job)

    args = subprocess.execute.await_args.args[0]
    assert "--no-subtitles" not in args
    assert ["--subtitle-tracks", "!3"] == args[3:5]


def test_track_name_for_known_and_unknown_codes() -> None:
    assert track_name_for("ara") == "Arabic"
    assert track_name_for("xyz") == "xyz"
    assert track_name_for(None) is None


# --- C8: the new file is checked before it may replace the original ---


def test_verifier_accepts_a_correct_remux() -> None:
    before = _identify([{"language": "eng", "default_track": True}], attachments=2)
    after = _identify(
        [
            {"language": "eng", "default_track": False},
            {"language": "ara", "language_ietf": "ar", "default_track": True},
        ],
        attachments=4,
    )
    assert verify_mux_output(before, after, _job()) == []


def test_verifier_rejects_missing_language_lost_tracks_and_short_files() -> None:
    before = _identify([{"language": "eng"}], attachments=3)
    after = _identify([{"language": "und"}], attachments=1, duration=1_000_000_000)
    after["tracks"] = [t for t in after["tracks"] if t["type"] != "audio"]

    problems = verify_mux_output(before, after, _job())

    assert any("audio tracks changed" in p for p in problems)
    assert any("expected 2 subtitle tracks" in p for p in problems)
    assert any("no subtitle track tagged 'ara'" in p for p in problems)
    assert any("attachments dropped" in p for p in problems)
    assert any("shorter" in p for p in problems)


def test_verifier_requires_default_flag_when_asked() -> None:
    before = _identify([])
    after = _identify([{"language": "ara", "default_track": False}])
    assert verify_mux_output(before, after, _job()) == [
        "the 'ara' track is not marked default"
    ]


def test_expected_subtitle_count_for_replacement() -> None:
    before = _identify([{"language": "ara"}, {"language": "eng"}])
    assert expected_subtitle_count(before, _job()) == 3
    replaced = _job(replace_embedded_subtitles=True, replaced_track_id=2)
    assert expected_subtitle_count(before, replaced) == 2


def _runner(
    tmp_path: Path, identify: AsyncMock, mux_ok: bool = True
) -> tuple[PipelineRunner, MagicMock, Path]:
    episode = tmp_path / "ep1.mkv"
    subtitle = tmp_path / "ep1.ass"
    episode.write_bytes(b"ORIGINAL")
    subtitle.write_text(
        "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default, Arial", "utf-8"
    )
    scan = LibraryScanResult(
        episode_path=episode, subtitle_path=subtitle, anime_title="Show"
    )
    scanner = MagicMock(spec=LibraryScanner)
    scanner.scan = AsyncMock(
        return_value=LibraryScanOutput(episodes=[scan], font_directories=[])
    )
    resolver = MagicMock(spec=FontResolver)
    resolver.for_run.return_value = resolver
    resolver.resolve = AsyncMock(side_effect=Exception("no fonts in this test"))
    subprocess = MagicMock(spec=SubprocessPort)
    subprocess.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="mkvmerge",
            success=mux_ok,
            exit_code=0 if mux_ok else 2,
            stdout="",
            stderr="",
            duration_ms=1.0,
        )
    )
    filesystem = MagicMock()
    filesystem.move_to_trash = AsyncMock()
    filesystem.replace_file = AsyncMock()
    filesystem.ensure_directory = AsyncMock()
    filesystem.write_file_atomic = AsyncMock()
    registry = MagicMock(spec=ToolRegistry)
    registry.is_available.return_value = False
    ingestion = MagicMock(spec=FontIngestionService)
    ingestion.ingest_directories = AsyncMock()
    mkvmerge = MagicMock()
    mkvmerge.identify = identify
    runner = PipelineRunner(
        font_resolver=resolver,
        subprocess_adapter=subprocess,
        filesystem=filesystem,
        tool_registry=registry,
        config=AppConfig(),
        font_ingestion_service=ingestion,
        disk_semaphore=asyncio.Semaphore(2),
        library_scanner=scanner,
        mkvmerge=mkvmerge,
    )
    return runner, subprocess, episode


@pytest.mark.anyio
async def test_failed_check_keeps_the_original_untouched(tmp_path: Path) -> None:
    before = _identify([{"language": "eng", "default_track": True}])
    broken = _identify([])  # mkvmerge produced a file without any subtitle
    identify = AsyncMock(side_effect=[before, broken])
    runner, _subprocess, _episode = _runner(tmp_path, identify)

    report = await runner.run(PipelineConfig(library_path=tmp_path))

    episode_report = report.episodes[0]
    assert episode_report.status == EpisodeStatus.FAILED
    assert any("failed the check" in rule for rule in episode_report.applied_rules)
    runner.filesystem.move_to_trash.assert_not_awaited()  # type: ignore[attr-defined]
    runner.filesystem.replace_file.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_good_check_swaps_and_muxes_the_repaired_subtitle(
    tmp_path: Path,
) -> None:
    before = _identify([{"language": "eng", "default_track": True}])
    good = _identify(
        [
            {"language": "eng", "default_track": False},
            {"language": "ara", "default_track": True},
        ]
    )
    identify = AsyncMock(side_effect=[before, good])
    runner, subprocess, episode = _runner(tmp_path, identify)

    report = await runner.run(PipelineConfig(library_path=tmp_path))

    assert report.episodes[0].status == EpisodeStatus.PARTIAL  # fonts missing
    args = subprocess.execute.await_args.args[0]
    # The repaired copy is muxed, not the untouched original.
    assert str(tmp_path / "ep1.tmp.ass") in args
    assert ["--default-track-flag", "2:no"] == args[3:5]
    runner.filesystem.replace_file.assert_awaited_once()  # type: ignore[attr-defined]
    moved = [c.args[0] for c in runner.filesystem.move_to_trash.await_args_list]  # type: ignore[attr-defined]
    assert moved == [episode, tmp_path / "ep1.ass"]


# --- C9: checkpoint paths survive Windows backslashes ---


@pytest.mark.anyio
async def test_checkpoint_round_trips_windows_paths(tmp_path: Path) -> None:
    manager = CheckpointManager(tmp_path)
    checkpoint = PipelineCheckpoint(
        library_path="D:\\Entertainment\\Anime",
        completed_episodes=('D:\\Entertainment\\Anime\\Show "A"\\ep1.mkv',),
        timestamp=NOW.isoformat(),
        selected_paths=(),
    )

    await manager.save(checkpoint)
    loaded = await manager.load()

    assert loaded is not None
    assert loaded.library_path == "D:\\Entertainment\\Anime"
    assert loaded.completed_episodes == checkpoint.completed_episodes


# --- Subtitle encodings used by Arabic releases ---


@pytest.mark.parametrize(
    "encoded",
    [
        "مرحبا".encode("cp1256"),
        "مرحبا".encode("utf-16"),
        "\ufeffمرحبا".encode("utf-8"),
        "مرحبا".encode("utf-8"),
    ],
)
def test_decode_subtitle_bytes_handles_arabic_encodings(encoded: bytes) -> None:
    assert decode_subtitle_bytes(encoded) == "مرحبا"
