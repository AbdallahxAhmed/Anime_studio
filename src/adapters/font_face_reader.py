"""fontTools-based read-only font face reader (Wave 0).

Opens font files strictly read-only (R1), iterates every face including
all faces in .ttc collections, and returns structured identity facts.

The reader:
  - Records name IDs 1, 4, 6, 16, and 21 with platform-aware decoding.
  - Records cmap coverage as compact codepoint ranges.
  - Records the weight and slant the face declares.
  - Never infers coverage or identity from filenames (R6).
  - Never lets a raw fontTools exception escape (R7); returns a result
    with ``unverifiable_reason`` set instead.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fontTools.ttLib import TTCollection, TTFont  # type: ignore[import-untyped]

from src.models.renderability import AttachmentFace, CodepointRange, FaceNameRecord

logger = structlog.get_logger()

# Name IDs we always record.  W0-C may restrict which of these libass
# actually honours; we record all of them so the data is available.
_RECORDED_NAME_IDS: frozenset[int] = frozenset({1, 4, 6, 16, 21})


def _codepoints_to_ranges(codepoints: set[int]) -> list[CodepointRange]:
    """Convert a set of codepoints to a sorted list of inclusive ranges."""
    if not codepoints:
        return []
    sorted_cps = sorted(codepoints)
    ranges: list[CodepointRange] = []
    start = sorted_cps[0]
    end = sorted_cps[0]
    for cp in sorted_cps[1:]:
        if cp == end + 1:
            end = cp
        else:
            ranges.append(CodepointRange(start=start, end=end))
            start = cp
            end = cp
    ranges.append(CodepointRange(start=start, end=end))
    return ranges


def _extract_name_records(tt: TTFont, face_index: int) -> list[FaceNameRecord]:
    """Extract name records for the IDs we track, with platform-aware decoding."""
    records: list[FaceNameRecord] = []
    name_table = tt.get("name")
    if name_table is None:
        return records
    for record in name_table.names:
        if record.nameID not in _RECORDED_NAME_IDS:
            continue
        try:
            value = record.toUnicode()
        except (UnicodeDecodeError, AttributeError):
            # Undecodable name record; skip rather than crash.
            logger.debug(
                "skipping undecodable name record",
                face_index=face_index,
                name_id=record.nameID,
                platform_id=record.platformID,
            )
            continue
        records.append(
            FaceNameRecord(
                name_id=record.nameID,
                platform_id=record.platformID,
                encoding_id=record.platEncID,
                language_id=record.langID,
                value=value,
            )
        )
    return records


def _extract_cmap_ranges(tt: TTFont) -> list[CodepointRange]:
    """Extract cmap coverage as compact inclusive codepoint ranges."""
    cmap_table = tt.get("cmap")
    if cmap_table is None:
        return []
    codepoints: set[int] = set()
    for table in cmap_table.tables:
        if hasattr(table, "cmap") and table.cmap:
            codepoints.update(table.cmap.keys())
    return _codepoints_to_ranges(codepoints)


def _extract_weight(tt: TTFont) -> int | None:
    """Extract the usWeightClass from the OS/2 table, if present."""
    os2 = tt.get("OS/2")
    if os2 is None:
        return None
    weight: int = os2.usWeightClass
    return weight


def _extract_slant(tt: TTFont) -> str | None:
    """Determine slant from the OS/2 fsSelection and macStyle bits."""
    os2 = tt.get("OS/2")
    if os2 is not None:
        fs_selection: int = os2.fsSelection
        if fs_selection & (1 << 0):  # bit 0 = ITALIC
            return "italic"
        if fs_selection & (1 << 9):  # bit 9 = OBLIQUE
            return "oblique"
    head = tt.get("head")
    if head is not None:
        mac_style: int = head.macStyle
        if mac_style & (1 << 1):  # bit 1 = italic
            return "italic"
    return None


def _read_single_face(tt: TTFont, face_index: int) -> AttachmentFace:
    """Read identity facts from a single TTFont object."""
    if "name" not in tt:
        return AttachmentFace(
            face_index=face_index,
            unverifiable_reason="Font is malformed or truncated: missing name table",
        )
    name_records = _extract_name_records(tt, face_index)
    cmap_ranges = _extract_cmap_ranges(tt)
    weight = _extract_weight(tt)
    slant = _extract_slant(tt)
    return AttachmentFace(
        face_index=face_index,
        name_records=name_records,
        cmap_ranges=cmap_ranges,
        weight=weight,
        slant=slant,
    )


class FontFaceReaderAdapter:
    """fontTools-based implementation of the font face reader.

    Opens every font file strictly read-only.  For font collections
    (.ttc), iterates every face.  Never raises on malformed or truncated
    fonts — returns a result with ``unverifiable_reason`` instead.
    """

    def read_faces(self, font_path: Path) -> list[AttachmentFace]:
        """Read all faces from the font file at *font_path*.

        Parameters
        ----------
        font_path:
            Path to the font file.  Opened read-only.

        Returns
        -------
        list[AttachmentFace]
            One entry per face.  On error, a single-element list with
            ``unverifiable_reason`` set.
        """
        try:
            return self._read_faces_impl(font_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "font file unreadable, marking as unverifiable",
                font_path=str(font_path),
                error=str(exc),
            )
            return [
                AttachmentFace(
                    face_index=0,
                    unverifiable_reason=f"Failed to read font: {exc}",
                )
            ]

    def _read_faces_impl(self, font_path: Path) -> list[AttachmentFace]:
        """Inner implementation; may raise on malformed fonts."""
        # Detect TTC by reading the first 4 bytes of the file signature.
        with open(font_path, "rb") as f:
            tag = f.read(4)
        is_collection = tag == b"ttcf"

        if is_collection:
            return self._read_collection(font_path)
        return self._read_single(font_path)

    def _read_collection(self, font_path: Path) -> list[AttachmentFace]:
        """Read all faces from a TTC font collection."""
        collection = TTCollection(str(font_path))
        faces: list[AttachmentFace] = []
        try:
            for idx, tt in enumerate(collection.fonts):
                faces.append(_read_single_face(tt, idx))
        finally:
            collection.close()
        return faces

    def _read_single(self, font_path: Path) -> list[AttachmentFace]:
        """Read a single-face font file."""
        tt = TTFont(str(font_path), fontNumber=0)
        try:
            face = _read_single_face(tt, 0)
        finally:
            tt.close()
        return [face]
