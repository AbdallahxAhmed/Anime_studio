from pathlib import Path
import structlog
from src.models.pipeline import EpisodeContext
from src.models.subtitle import SubtitleSource
from src.models.mux import MuxJob

logger = structlog.get_logger()


def plan_mux(
    context: EpisodeContext,
    output_path: Path,
    dry_run: bool = False,
) -> MuxJob:
    """Build a MuxJob from an EpisodeContext, specifying target output path and dry_run flag."""
    logger.info(
        "planning mux job",
        episode=context.scan_result.episode_path.name,
        output=output_path,
        dry_run=dry_run,
    )
    assert context.scan_result.subtitle_path is not None, (
        "Subtitle path required for muxing"
    )
    replace_embedded = context.scan_result.subtitle_source == SubtitleSource.EMBEDDED
    return MuxJob(
        episode_path=context.scan_result.episode_path,
        subtitle_path=context.scan_result.subtitle_path,
        fonts=context.resolved_fonts,
        dry_run=dry_run,
        output_path=output_path,
        replace_embedded_subtitles=replace_embedded,
    )
