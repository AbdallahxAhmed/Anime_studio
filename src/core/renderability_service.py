"""Renderability service (Feature 013).

Composes the three pieces of subtitle forensics into one call:

1. read the identity facts of every font file through ``FontFaceReaderPort``
   (blocking file I/O, so it runs in a worker thread, Constitution III);
2. extract styles and per-style font requirements from the subtitle text;
3. hand both to the pure :class:`RenderabilityEngine`.

The service holds no state between calls (Constitution: stateless services) and
mocks nothing: the only collaborator is the port, so tests supply a fake reader
or the real adapter.

Fonts are judged as **planned attachments**: each file the pipeline will mux
becomes an ``Attachment`` numbered from 1 in mux order, the way mkvmerge numbers
attachments.  Faces are always read from the file itself; a resolver's claim
about what a file contains is never trusted (R5), and the filename is never
identity (R6).
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import platform
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from src.core.renderability_engine import RenderabilityEngine
from src.core.subtitle_requirements import extract_subtitle_requirements
from src.models.renderability import (
    Attachment,
    AttachmentFace,
    Environment,
    ProvenanceEntry,
    RenderabilityReport,
    SubtitleTrack,
)
from src.ports.font_face_reader import FontFaceReaderPort

DEFAULT_TRACK: Final[SubtitleTrack] = SubtitleTrack(
    track_id=0, codec="ass", language="", is_default=True
)
"""Track used for an external subtitle file."""

_MIME_BY_SUFFIX: Final[dict[str, str]] = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".ttc": "font/collection",
    ".otc": "font/collection",
}
"""Container classification by extension.  Informational only (never identity)."""


def capture_environment() -> Environment:
    """Record the runtime facts a report was produced under."""
    try:
        fonttools_version = importlib.metadata.version("fonttools")
    except importlib.metadata.PackageNotFoundError:
        fonttools_version = ""
    return Environment(
        fonttools_version=fonttools_version,
        python_version=platform.python_version(),
        platform=platform.platform(),
    )


class RenderabilityService:
    """Produce a :class:`RenderabilityReport` for one subtitle and its fonts."""

    def __init__(
        self,
        face_reader: FontFaceReaderPort,
        *,
        engine: RenderabilityEngine | None = None,
    ) -> None:
        self._face_reader = face_reader
        self._engine = (
            engine
            if engine is not None
            else RenderabilityEngine(environment=capture_environment())
        )

    async def analyse(
        self,
        *,
        episode_path: Path | str,
        subtitle_content: str,
        font_paths: Sequence[Path],
        track: SubtitleTrack | None = None,
    ) -> RenderabilityReport:
        """Judge whether *font_paths* can render *subtitle_content*.

        Parameters
        ----------
        episode_path:
            The episode the subtitle belongs to; recorded in the report only.
        subtitle_content:
            ASS/SSA script text.
        font_paths:
            Font files that will be attached.  Duplicates are read once.  An
            unreadable file yields an unverifiable face, never an exception.
        track:
            Describes the subtitle track; defaults to an external ASS file.
        """
        subtitle_track = track if track is not None else DEFAULT_TRACK
        unique_paths = list(dict.fromkeys(Path(p) for p in font_paths))

        extracted = await asyncio.to_thread(
            extract_subtitle_requirements,
            subtitle_content,
            track_id=subtitle_track.track_id,
        )
        attachments = await asyncio.to_thread(self._read_attachments, unique_paths)

        now = self._engine.now
        provenance = [
            ProvenanceEntry(
                action="subtitle_parsed",
                timestamp=now(),
                detail=(
                    f"track={subtitle_track.track_id} styles={len(extracted.styles)} "
                    f"dialogue_lines={extracted.dialogue_lines} "
                    f"skipped_lines={extracted.skipped_lines} "
                    f"requirements={len(extracted.requirements)}"
                ),
            )
        ]
        for path, attachment in zip(unique_paths, attachments, strict=True):
            unreadable = sum(1 for f in attachment.faces if f.unverifiable_reason)
            provenance.append(
                ProvenanceEntry(
                    action="font_file_read",
                    timestamp=now(),
                    detail=(
                        f"attachment_id={attachment.attachment_id} file={path.name!r} "
                        f"faces={len(attachment.faces)} unreadable_faces={unreadable}"
                    ),
                )
            )

        return await asyncio.to_thread(
            self._engine.evaluate,
            episode_path=str(episode_path),
            attachments=attachments,
            subtitle_tracks=[subtitle_track],
            styles=extracted.styles,
            requirements=extracted.requirements,
            warnings=extracted.warnings,
            provenance=provenance,
        )

    # -- internals ---------------------------------------------------------

    def _read_attachments(self, paths: Sequence[Path]) -> list[Attachment]:
        """Read every font file (runs in a worker thread)."""
        attachments: list[Attachment] = []
        for number, path in enumerate(paths, start=1):
            try:
                faces = self._face_reader.read_faces(path)
            except OSError as exc:  # the port promises not to raise; be safe anyway
                faces = [
                    AttachmentFace(
                        face_index=0,
                        unverifiable_reason=f"font file could not be read: {exc}",
                    )
                ]
            attachments.append(
                Attachment(
                    attachment_id=number,
                    attachment_filename=path.name,
                    mime_type=_MIME_BY_SUFFIX.get(path.suffix.lower(), ""),
                    faces=faces,
                )
            )
        return attachments
