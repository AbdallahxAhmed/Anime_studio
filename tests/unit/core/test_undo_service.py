import pytest
from unittest.mock import AsyncMock, MagicMock
from src.models.run_manifest import RunManifest, EpisodeProcessed
from src.core.undo_service import UndoService
from src.ports.filesystem import FilesystemPort


@pytest.fixture
def mock_fs():
    fs = MagicMock(spec=FilesystemPort)
    fs.replace_file = AsyncMock()
    return fs


@pytest.mark.anyio
async def test_save_and_list_runs(tmp_path, mock_fs):
    service = UndoService(tmp_path, mock_fs, max_run_history=2)

    ep = EpisodeProcessed(episode_path="/a/b.mkv", status="success")
    manifest1 = RunManifest(
        run_id="run-1",
        timestamp="2026-06-07T12:00:00Z",
        library_path="/anime",
        episodes_processed=(ep,),
    )
    manifest2 = RunManifest(
        run_id="run-2",
        timestamp="2026-06-07T13:00:00Z",
        library_path="/anime",
        episodes_processed=(ep,),
    )

    await service.save_manifest(manifest1)
    await service.save_manifest(manifest2)

    runs = await service.list_runs()
    assert len(runs) == 2
    # Sorted descending by timestamp
    assert runs[0].run_id == "run-2"
    assert runs[1].run_id == "run-1"


@pytest.mark.anyio
async def test_prune_old_manifests(tmp_path, mock_fs):
    service = UndoService(tmp_path, mock_fs, max_run_history=2)

    for i in range(5):
        manifest = RunManifest(
            run_id=f"run-{i}",
            timestamp=f"2026-06-07T12:00:0{i}Z",
            library_path="/anime",
            episodes_processed=(),
        )
        await service.save_manifest(manifest)

    runs = await service.list_runs()
    assert len(runs) == 2


@pytest.mark.anyio
async def test_undo_episode_success(tmp_path, mock_fs):
    service = UndoService(tmp_path, mock_fs)

    trash_file = tmp_path / "trash_ep.mkv"
    trash_file.touch()
    dest_file = tmp_path / "original_ep.mkv"  # Doesn't exist initially

    ep = EpisodeProcessed(
        episode_path=dest_file, trash_receipt_path=trash_file, status="success"
    )
    manifest = RunManifest(
        run_id="run-1",
        timestamp="2026-06-07T12:00:00Z",
        library_path=tmp_path,
        episodes_processed=(ep,),
    )

    await service.save_manifest(manifest)

    result = await service.undo_episode(manifest, str(dest_file))
    assert result.restored == 1
    assert result.failed == 0
    assert result.missing == 0
    assert result.conflicts == 0

    # Assert mock_fs.replace_file was called
    mock_fs.replace_file.assert_called_once_with(trash_file, dest_file)


@pytest.mark.anyio
async def test_undo_episode_missing_trash(tmp_path, mock_fs):
    service = UndoService(tmp_path, mock_fs)

    trash_file = tmp_path / "nonexistent_trash_ep.mkv"
    dest_file = tmp_path / "original_ep.mkv"

    ep = EpisodeProcessed(
        episode_path=dest_file, trash_receipt_path=trash_file, status="success"
    )
    manifest = RunManifest(
        run_id="run-1",
        timestamp="2026-06-07T12:00:00Z",
        library_path=tmp_path,
        episodes_processed=(ep,),
    )

    result = await service.undo_episode(manifest, str(dest_file))
    assert result.restored == 0
    assert result.missing == 1
    mock_fs.replace_file.assert_not_called()


@pytest.mark.anyio
async def test_undo_episode_conflict(tmp_path, mock_fs):
    service = UndoService(tmp_path, mock_fs)

    trash_file = tmp_path / "trash_ep.mkv"
    trash_file.touch()
    dest_file = tmp_path / "original_ep.mkv"
    dest_file.touch()  # Exists already!

    ep = EpisodeProcessed(
        episode_path=dest_file, trash_receipt_path=trash_file, status="success"
    )
    manifest = RunManifest(
        run_id="run-1",
        timestamp="2026-06-07T12:00:00Z",
        library_path=tmp_path,
        episodes_processed=(ep,),
    )

    result = await service.undo_episode(manifest, str(dest_file))
    assert result.restored == 0
    assert result.conflicts == 1
    mock_fs.replace_file.assert_not_called()


@pytest.mark.anyio
async def test_manifest_windows_paths_round_trip_and_malformed_history_is_skipped(
    tmp_path, mock_fs
):
    """One historical bad TOML file cannot hide a valid Windows-path manifest."""
    service = UndoService(tmp_path, mock_fs)
    manifest = RunManifest(
        run_id="windows-run",
        timestamp="2026-07-23T00:48:00+00:00",
        library_path=r"D:\Entertainment\Anime",
        episodes_processed=(
            EpisodeProcessed(
                episode_path=r"D:\Entertainment\Anime\Show A\01.mkv",
                trash_receipt_path=r"D:\Entertainment\.anime_studio_trash\01.mkv",
                show_name="Show A",
                status="success",
            ),
        ),
    )
    await service.save_manifest(manifest)
    service.history_dir.mkdir(parents=True, exist_ok=True)
    malformed = service.history_dir / "run_bad.toml"
    malformed.write_text('library_path = "D:\\broken\\path"', encoding="utf-8")

    runs = await service.list_runs()
    assert [run.run_id for run in runs] == ["windows-run"]
    assert str(runs[0].library_path) == r"D:\Entertainment\Anime"
    assert str(runs[0].episodes_processed[0].episode_path) == (
        r"D:\Entertainment\Anime\Show A\01.mkv"
    )

    # The malformed historical file remains untouched and subsequent loads
    # continue to expose the valid manifest.
    assert malformed.is_file()
    assert [run.run_id for run in await service.list_runs()] == ["windows-run"]
