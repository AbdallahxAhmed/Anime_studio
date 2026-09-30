"""Contract tests for the FontFaceReaderPort protocol.

Follows the pattern of tests/contract/test_hunter_protocol.py.
"""

from pathlib import Path

from src.adapters.font_face_reader import FontFaceReaderAdapter
from src.models.renderability import AttachmentFace
from src.ports.font_face_reader import FontFaceReaderPort


class ConformingReader:
    """Minimal conforming implementation for protocol checks."""

    def read_faces(self, font_path: Path) -> list[AttachmentFace]:
        return [AttachmentFace(face_index=0)]


class NonConformingReader:
    """Missing the read_faces method entirely."""


def test_font_face_reader_protocol_conformance() -> None:
    reader = ConformingReader()
    assert isinstance(reader, FontFaceReaderPort)


def test_font_face_reader_protocol_non_conformance() -> None:
    reader = NonConformingReader()
    assert not isinstance(reader, FontFaceReaderPort)


def test_adapter_conforms_to_protocol() -> None:
    adapter = FontFaceReaderAdapter()
    assert isinstance(adapter, FontFaceReaderPort)
