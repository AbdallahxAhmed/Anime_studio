"""Check a freshly muxed file before it is allowed to replace the original.

Pure functions over ``mkvmerge -J`` output: no I/O, easy to test.
"""

from typing import Any

from src.models.mux import MuxJob

# A remuxed file may differ from the source by container overhead only.
_DURATION_TOLERANCE = 0.01


def _tracks(identify: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    tracks = identify.get("tracks") or []
    return [t for t in tracks if isinstance(t, dict) and t.get("type") == kind]


def _duration_ns(identify: dict[str, Any]) -> int | None:
    container = identify.get("container") or {}
    properties = container.get("properties") or {}
    value = properties.get("duration")
    return int(value) if isinstance(value, (int, float)) and value > 0 else None


def _language_matches(track: dict[str, Any], language: str) -> bool:
    properties = track.get("properties") or {}
    wanted = language.lower()
    code = str(properties.get("language") or "").lower()
    ietf = str(properties.get("language_ietf") or "").lower()
    if code == wanted or ietf == wanted:
        return True
    # "ara" <-> "ar", "eng" <-> "en"
    return bool(ietf) and len(wanted) == 3 and ietf.split("-")[0] == wanted[:2]


def expected_subtitle_count(before: dict[str, Any], job: MuxJob) -> int:
    existing = len(_tracks(before, "subtitles"))
    if job.replace_embedded_subtitles:
        existing = existing - 1 if job.replaced_track_id is not None else 0
    return max(existing, 0) + 1


def verify_mux_output(
    before: dict[str, Any], after: dict[str, Any], job: MuxJob
) -> list[str]:
    """Return the problems found in ``after``; an empty list means it is safe."""
    problems: list[str] = []

    for kind in ("video", "audio"):
        had = len(_tracks(before, kind))
        has = len(_tracks(after, kind))
        if has != had:
            problems.append(f"{kind} tracks changed from {had} to {has}")

    subtitles = _tracks(after, "subtitles")
    wanted = expected_subtitle_count(before, job)
    if len(subtitles) != wanted:
        problems.append(f"expected {wanted} subtitle tracks, found {len(subtitles)}")

    if job.subtitle_language:
        matching = [t for t in subtitles if _language_matches(t, job.subtitle_language)]
        if not matching:
            problems.append(f"no subtitle track tagged '{job.subtitle_language}'")
        elif job.make_default and not any(
            (t.get("properties") or {}).get("default_track") for t in matching
        ):
            problems.append(
                f"the '{job.subtitle_language}' track is not marked default"
            )

    attachments_before = len(before.get("attachments") or [])
    attachments_after = len(after.get("attachments") or [])
    if attachments_after < attachments_before:
        problems.append(
            f"attachments dropped from {attachments_before} to {attachments_after}"
        )

    duration_before = _duration_ns(before)
    duration_after = _duration_ns(after)
    if duration_before and duration_after:
        if duration_after < duration_before * (1 - _DURATION_TOLERANCE):
            problems.append("new file is shorter than the original")

    return problems
