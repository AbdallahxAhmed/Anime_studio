import pytest
from src.models.run_manifest import PipelineCheckpoint
from src.core.checkpoint_manager import CheckpointManager


@pytest.mark.anyio
async def test_checkpoint_manager_roundtrip(tmp_path):
    mgr = CheckpointManager(tmp_path)

    # Save checkpoint
    cp = PipelineCheckpoint(
        library_path=tmp_path / "lib",
        completed_episodes=("/lib/ep1.mkv", "/lib/ep2.mkv"),
        timestamp="2026-06-07T12:00:00Z",
        selected_paths=("/lib/Show A",),
    )
    await mgr.save(cp)

    # Load checkpoint
    loaded = await mgr.load()
    assert loaded is not None
    assert loaded.library_path == (tmp_path / "lib").as_posix()
    assert loaded.completed_episodes == ("/lib/ep1.mkv", "/lib/ep2.mkv")
    assert loaded.timestamp == "2026-06-07T12:00:00Z"
    assert loaded.selected_paths == ("/lib/Show A",)


@pytest.mark.anyio
async def test_checkpoint_manager_missing(tmp_path):
    mgr = CheckpointManager(tmp_path)
    loaded = await mgr.load()
    assert loaded is None


@pytest.mark.anyio
async def test_checkpoint_manager_corrupt(tmp_path):
    mgr = CheckpointManager(tmp_path)
    # Write invalid data
    mgr.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    mgr.checkpoint_path.write_text("invalid_toml = [", encoding="utf-8")

    loaded = await mgr.load()
    assert loaded is None


@pytest.mark.anyio
async def test_checkpoint_manager_clear(tmp_path):
    mgr = CheckpointManager(tmp_path)
    cp = PipelineCheckpoint(
        library_path=tmp_path, completed_episodes=(), timestamp="now", selected_paths=()
    )
    await mgr.save(cp)
    assert mgr.checkpoint_path.is_file()

    await mgr.clear()
    assert not mgr.checkpoint_path.is_file()
    assert await mgr.load() is None


@pytest.mark.anyio
async def test_checkpoint_manager_exists_for_library(tmp_path):
    mgr = CheckpointManager(tmp_path)
    lib1 = tmp_path / "lib1"
    lib2 = tmp_path / "lib2"

    cp = PipelineCheckpoint(
        library_path=lib1, completed_episodes=(), timestamp="now", selected_paths=()
    )
    await mgr.save(cp)

    assert mgr.exists_for_library(lib1) is True
    assert mgr.exists_for_library(lib2) is False
