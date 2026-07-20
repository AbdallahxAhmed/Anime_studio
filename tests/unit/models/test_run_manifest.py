import pytest
from pathlib import Path
from dataclasses import FrozenInstanceError
from src.models.run_manifest import EpisodeProcessed, RunManifest, PipelineCheckpoint


def test_episode_processed_construction():
    ep = EpisodeProcessed(
        episode_path=Path("/test/episode_01.mkv"),
        trash_receipt_path=Path("/test/trash.json"),
        show_name="Anime A",
        status="success",
    )
    assert ep.episode_path == "/test/episode_01.mkv"
    assert ep.trash_receipt_path == "/test/trash.json"
    assert ep.show_name == "Anime A"
    assert ep.status == "success"


def test_episode_processed_immutability():
    ep = EpisodeProcessed(episode_path="/test/ep.mkv", status="success")
    with pytest.raises(FrozenInstanceError):
        ep.episode_path = "/test/new.mkv"


def test_run_manifest_construction():
    ep1 = EpisodeProcessed(
        episode_path="/test/ep1.mkv", show_name="Show A", status="success"
    )
    ep2 = EpisodeProcessed(
        episode_path="/test/ep2.mkv", show_name="Show A", status="failed"
    )
    manifest = RunManifest(
        run_id="run-123",
        timestamp="2026-06-07T12:00:00Z",
        library_path=Path("/anime"),
        episodes_processed=(ep1, ep2),
    )
    assert manifest.run_id == "run-123"
    assert manifest.timestamp == "2026-06-07T12:00:00Z"
    assert manifest.library_path == "/anime"
    assert len(manifest.episodes_processed) == 2
    assert manifest.success_count == 1
    assert manifest.show_names == ["Show A"]


def test_pipeline_checkpoint_construction():
    checkpoint = PipelineCheckpoint(
        library_path=Path("/anime"),
        completed_episodes=("/anime/ep1.mkv", Path("/anime/ep2.mkv")),
        timestamp="2026-06-07T12:00:00Z",
        selected_paths=(Path("/anime/Show A"), "/anime/Show B"),
    )
    assert checkpoint.library_path == "/anime"
    assert checkpoint.completed_episodes == ("/anime/ep1.mkv", "/anime/ep2.mkv")
    assert checkpoint.selected_paths == ("/anime/Show A", "/anime/Show B")
