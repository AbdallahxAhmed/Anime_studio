"""Port (typing.Protocol) for the read-only font face reader.

The reader opens a font file, iterates every face (including all faces
in a .ttc collection), and returns structured identity facts without
writing to or mutating the input file (R1).

Implementations MUST NOT raise on malformed or truncated fonts; they
return a result carrying an ``unverifiable_reason`` instead (R7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from src.models.renderability import AttachmentFace


@runtime_checkable
class FontFaceReaderPort(Protocol):
    """Read-only font face reader protocol.

    Implementations extract identity facts (name records, cmap coverage,
    weight, slant) from font files.  They never write to or mutate input
    files (R1), never infer identity from filenames (R6), and never let
    raw exceptions escape (R7).
    """

    def read_faces(self, font_path: Path) -> list[AttachmentFace]:
        """Read all faces from the font file at *font_path*.

        For font collections (.ttc), every face is returned, not only
        the first.

        If the file is malformed, truncated, or unreadable, the
        implementation MUST NOT raise.  It returns a single-element list
        with ``unverifiable_reason`` set instead.

        Parameters
        ----------
        font_path:
            Absolute or relative path to the font file.  The file is
            opened strictly read-only.

        Returns
        -------
        list[AttachmentFace]
            One entry per face in the file.
        """
        ...
