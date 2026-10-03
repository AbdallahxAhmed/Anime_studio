"""Build real minimal fonts for renderability tests.

Every font is generated at test time with ``fontTools.fontBuilder`` inside a
temporary directory; no binary font files are committed (same approach as the
Wave 0 reader tests).  Not a test module: pytest does not collect it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fontTools.fontBuilder import FontBuilder  # type: ignore[import-untyped]
from fontTools.pens.ttGlyphPen import TTGlyphPen  # type: ignore[import-untyped]
from fontTools.ttLib import TTCollection, TTFont  # type: ignore[import-untyped]

LATIN: frozenset[int] = frozenset(range(0x20, 0x7F))
ARABIC: frozenset[int] = frozenset({0x20, 0x200F} | set(range(0x0600, 0x0700)))


def span(*ranges: tuple[int, int]) -> frozenset[int]:
    """Return every codepoint in the inclusive *ranges*."""
    covered: set[int] = set()
    for start, end in ranges:
        covered.update(range(start, end + 1))
    return frozenset(covered)


@dataclass(frozen=True)
class FaceSpec:
    """What one face of a generated font declares."""

    family: str
    codepoints: frozenset[int] = LATIN
    style: str = "Regular"
    weight: int = 400
    italic: bool = False
    typographic_family: str | None = None
    full_name: str | None = None


def _make_font(spec: FaceSpec) -> TTFont:
    glyph_names = [".notdef"] + [f"glyph_{cp}" for cp in sorted(spec.codepoints)]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_names)
    builder.setupCharacterMap({cp: f"glyph_{cp}" for cp in sorted(spec.codepoints)})

    glyphs = {}
    for name in glyph_names:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((500, 0))
        pen.lineTo((500, 700))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (500, 0) for name in glyph_names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)

    bold = spec.weight >= 700
    selection = (1 if spec.italic else 0) | (32 if bold else 0)
    if not spec.italic and not bold:
        selection |= 64  # REGULAR
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWeightClass=spec.weight,
        fsSelection=selection,
    )
    builder.setupPost()
    builder.setupHead(
        unitsPerEm=1000, macStyle=(1 if bold else 0) | (2 if spec.italic else 0)
    )
    builder.setupNameTable({"familyName": spec.family, "styleName": spec.style})

    font = builder.font
    names = font["name"]
    if spec.full_name is not None:
        names.setName(spec.full_name, 4, 3, 1, 0x0409)
    if spec.typographic_family is not None:
        names.setName(spec.typographic_family, 16, 3, 1, 0x0409)
        names.setName(spec.style, 17, 3, 1, 0x0409)
    return font


def build_font(directory: Path, filename: str, spec: FaceSpec) -> Path:
    """Write a single-face TrueType font and return its path."""
    path = directory / filename
    font = _make_font(spec)
    font.save(str(path))
    font.close()
    return path


def build_collection(directory: Path, filename: str, specs: Sequence[FaceSpec]) -> Path:
    """Write a TrueType collection (.ttc) with one face per spec."""
    path = directory / filename
    fonts = [_make_font(spec) for spec in specs]
    collection = TTCollection()
    collection.fonts = fonts
    collection.save(str(path))
    collection.close()
    for font in fonts:
        font.close()
    return path


def build_truncated(
    directory: Path, filename: str, source: Path, keep: int = 40
) -> Path:
    """Copy the first *keep* bytes of *source*: a truncated, unreadable font."""
    path = directory / filename
    path.write_bytes(source.read_bytes()[:keep])
    return path
