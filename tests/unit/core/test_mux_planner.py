from pathlib import Path
from src.core.mux_planner import plan_mux
from src.models.pipeline import EpisodeContext, LibraryScanResult
from src.models.font import FontAsset


def test_plan_mux_valid():
    scan = LibraryScanResult(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/anime/ep1.ass"),
        anime_title="My Anime",
    )
    font = FontAsset(
        name="Arial",
        file_path=Path("/fonts/arial.ttf"),
        source="system",
        layer_found=1,
        cache_hit=True,
        nameids={1: "Arial"},
    )
    context = EpisodeContext(
        scan_result=scan,
        resolved_fonts=[font],
    )

    out_path = Path("/output/ep1_muxed.mkv")
    job = plan_mux(context, out_path, dry_run=True)

    assert job.episode_path == Path("/anime/ep1.mkv")
    assert job.subtitle_path == Path("/anime/ep1.ass")
    assert job.fonts == [font]
    assert job.dry_run is True
    assert job.output_path == out_path
    assert job.replace_embedded_subtitles is False


def test_plan_mux_embedded_replaces_subtitles():
    from src.models.subtitle import SubtitleSource

    scan = LibraryScanResult(
        episode_path=Path("/anime/ep1.mkv"),
        subtitle_path=Path("/trash/extracted.tmp.ass"),
        subtitle_source=SubtitleSource.EMBEDDED,
        anime_title="My Anime",
    )
    context = EpisodeContext(
        scan_result=scan,
        resolved_fonts=[],
    )

    out_path = Path("/output/ep1_muxed.mkv")
    job = plan_mux(context, out_path)

    assert job.replace_embedded_subtitles is True
    assert job.episode_path == Path("/anime/ep1.mkv")
    assert job.subtitle_path == Path("/trash/extracted.tmp.ass")
