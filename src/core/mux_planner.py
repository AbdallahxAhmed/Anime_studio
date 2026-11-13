from pathlib import Path
import structlog
from src.models.pipeline import EpisodeContext
from src.models.subtitle import SubtitleSource
from src.models.mux import MuxJob

logger = structlog.get_logger()


_LANGUAGE_NAMES = {
    "ara": "Arabic",
    "eng": "English",
    "fre": "French",
    "fra": "French",
    "ger": "German",
    "deu": "German",
    "spa": "Spanish",
    "por": "Portuguese",
    "ind": "Indonesian",
    "tur": "Turkish",
    "jpn": "Japanese",
}


def track_name_for(language: str | None) -> str | None:
    """Human-readable track name for an ISO 639-2 code (None stays None)."""
    if not language:
        return None
    return _LANGUAGE_NAMES.get(language.lower(), language)


def plan_mux(
    context: EpisodeContext,
    output_path: Path,
    dry_run: bool = False,
    *,
    subtitle_path: Path | None = None,
    subtitle_language: str | None = None,
    make_default: bool = False,
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
        # The repaired (and possibly synced) copy when one was written.
        subtitle_path=subtitle_path or context.scan_result.subtitle_path,
        fonts=context.resolved_fonts,
        dry_run=dry_run,
        output_path=output_path,
        replace_embedded_subtitles=replace_embedded,
        subtitle_language=subtitle_language,
        subtitle_track_name=track_name_for(subtitle_language),
        make_default=make_default,
        replaced_track_id=(
            context.scan_result.selected_track_id if replace_embedded else None
        ),
    )
