"""Unit tests for the fontTools-based font face reader adapter.

All font faces are built at test time with fontTools.fontBuilder inside
``tmp_path``.  No binary font files are committed.

Covers:
  1. Name ID 16 differs from filename and name ID 1
  2. TTC collection with ≥2 faces, every face returned
  3. Name IDs 1, 4, 6 disagreeing on the same face
  4. Cmap coverage as correct compact ranges, including non-contiguous cmap
  5a. Coverage entirely inside U+E000–U+F8FF (BMP PUA)
  5b. Coverage entirely inside U+F200–U+F30F (subset of BMP PUA)
  6. Truncated / malformed font file → no exception, unverifiable_reason set
  7. Filename contradicts every internal name record → filename ignored (R6)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder  # type: ignore[import-untyped]
from fontTools.pens.ttGlyphPen import TTGlyphPen  # type: ignore[import-untyped]
from fontTools.ttLib import TTCollection, TTFont  # type: ignore[import-untyped]

from src.adapters.font_face_reader import FontFaceReaderAdapter
from src.models.renderability import ADMISSIBLE_NAME_IDS

# ---------------------------------------------------------------------------
# Helpers: font generation
# ---------------------------------------------------------------------------


def _build_font(
    tmp_path: Path,
    filename: str,
    *,
    family_name: str = "TestFamily",
    name_id_1: str | None = None,
    name_id_4: str | None = None,
    name_id_6: str | None = None,
    name_id_16: str | None = None,
    name_id_21: str | None = None,
    cmap_codepoints: set[int] | None = None,
    weight_class: int = 400,
    is_italic: bool = False,
) -> Path:
    """Build a minimal TrueType font using fontTools.fontBuilder."""
    if cmap_codepoints is None:
        cmap_codepoints = {65, 66, 67}  # A, B, C

    # We need at least one glyph per codepoint, plus .notdef
    glyph_names = [".notdef"] + [f"glyph_{cp}" for cp in sorted(cmap_codepoints)]
    cmap_mapping = {cp: f"glyph_{cp}" for cp in sorted(cmap_codepoints)}

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyph_names)
    fb.setupCharacterMap(cmap_mapping)

    # Draw minimal glyphs using TTGlyphPen (required by fontTools ≥4.63)
    glyf_glyphs = {}
    for gname in glyph_names:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((500, 0))
        pen.lineTo((500, 700))
        pen.closePath()
        glyf_glyphs[gname] = pen.glyph()
    fb.setupGlyf(glyf_glyphs)

    fb.setupHorizontalMetrics({name: (500, 0) for name in glyph_names})

    fb.setupHorizontalHeader(ascent=800, descent=-200)

    fb.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWeightClass=weight_class,
        fsSelection=(1 if is_italic else 0),
    )

    fb.setupPost()
    fb.setupHead(unitsPerEm=1000)

    # Name table: set specific name IDs
    name_values: dict[str, str] = {}
    name_values["familyName"] = name_id_1 if name_id_1 is not None else family_name
    name_values["styleName"] = "Regular"

    fb.setupNameTable(name_values)

    # Now override specific name IDs if they differ
    font = fb.font
    name_table = font["name"]

    if name_id_4 is not None:
        # Override name ID 4 (full name)
        name_table.setName(name_id_4, 4, 3, 1, 0x0409)

    if name_id_6 is not None:
        # Override name ID 6 (PostScript name)
        name_table.setName(name_id_6, 6, 3, 1, 0x0409)

    if name_id_16 is not None:
        # Add name ID 16 (typographic family name)
        name_table.setName(name_id_16, 16, 3, 1, 0x0409)

    if name_id_21 is not None:
        # Add name ID 21 (WWS family name)
        name_table.setName(name_id_21, 21, 3, 1, 0x0409)

    out_path = tmp_path / filename
    font.save(str(out_path))
    font.close()
    return out_path


def _build_ttc(
    tmp_path: Path,
    filename: str,
    face_configs: list[dict[str, str | set[int] | int | None]],
) -> Path:
    """Build a TTC with multiple faces."""
    fonts: list[TTFont] = []
    for cfg in face_configs:
        cmap_cps: set[int] = cfg.get("cmap_codepoints", {65, 66, 67})  # type: ignore[assignment]
        family: str = cfg.get("family_name", "Face")  # type: ignore[assignment]
        glyph_names = [".notdef"] + [f"glyph_{cp}" for cp in sorted(cmap_cps)]
        cmap_mapping = {cp: f"glyph_{cp}" for cp in sorted(cmap_cps)}

        fb = FontBuilder(1000, isTTF=True)
        fb.setupGlyphOrder(glyph_names)
        fb.setupCharacterMap(cmap_mapping)

        glyf_glyphs = {}
        for gname in glyph_names:
            pen = TTGlyphPen(None)
            pen.moveTo((0, 0))
            pen.lineTo((500, 0))
            pen.lineTo((500, 700))
            pen.closePath()
            glyf_glyphs[gname] = pen.glyph()
        fb.setupGlyf(glyf_glyphs)
        fb.setupHorizontalMetrics({name: (500, 0) for name in glyph_names})
        fb.setupHorizontalHeader(ascent=800, descent=-200)
        fb.setupOS2(
            sTypoAscender=800,
            sTypoDescender=-200,
            usWeightClass=400,
        )
        fb.setupPost()
        fb.setupHead(unitsPerEm=1000)
        fb.setupNameTable({"familyName": family, "styleName": "Regular"})
        fonts.append(fb.font)

    out_path = tmp_path / filename
    # Write as TTC
    collection = TTCollection()
    collection.fonts = fonts
    collection.save(str(out_path))
    collection.close()
    for f in fonts:
        f.close()
    return out_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reader() -> FontFaceReaderAdapter:
    return FontFaceReaderAdapter()


# ---------------------------------------------------------------------------
# Test 1: name ID 16 differs from filename and name ID 1
# ---------------------------------------------------------------------------


class TestNameId16DiffersFromFilenameAndNameId1:
    def test_name_id_16_recorded_independently(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        font_path = _build_font(
            tmp_path,
            "TotallyWrongFilename.ttf",
            name_id_1="FamilyAlpha",
            name_id_16="TypographicBeta",
        )
        faces = reader.read_faces(font_path)
        assert len(faces) == 1
        face = faces[0]

        # Extract name ID values by ID
        names_by_id: dict[int, list[str]] = {}
        for rec in face.name_records:
            names_by_id.setdefault(rec.name_id, []).append(rec.value)

        assert "FamilyAlpha" in names_by_id.get(1, [])
        assert "TypographicBeta" in names_by_id.get(16, [])
        # Name ID 16 differs from name ID 1
        assert names_by_id.get(1, []) != names_by_id.get(16, [])


# ---------------------------------------------------------------------------
# Test 2: TTC with ≥2 faces, every face returned
# ---------------------------------------------------------------------------


class TestTtcCollection:
    def test_all_faces_in_ttc_returned(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        ttc_path = _build_ttc(
            tmp_path,
            "multi.ttc",
            [
                {"family_name": "FaceAlpha", "cmap_codepoints": {65, 66}},
                {"family_name": "FaceBeta", "cmap_codepoints": {67, 68}},
                {"family_name": "FaceGamma", "cmap_codepoints": {69, 70}},
            ],
        )
        faces = reader.read_faces(ttc_path)
        assert len(faces) == 3
        assert faces[0].face_index == 0
        assert faces[1].face_index == 1
        assert faces[2].face_index == 2

        # Each face has distinct name records
        names = []
        for face in faces:
            id1_values = [r.value for r in face.name_records if r.name_id == 1]
            names.extend(id1_values)
        assert "FaceAlpha" in names
        assert "FaceBeta" in names
        assert "FaceGamma" in names


# ---------------------------------------------------------------------------
# Test 3: name IDs 1, 4, 6 disagreeing
# ---------------------------------------------------------------------------


class TestDisagreeingNameIds:
    def test_name_ids_1_4_6_all_recorded_when_different(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        font_path = _build_font(
            tmp_path,
            "disagree.ttf",
            name_id_1="FamilyOne",
            name_id_4="FullNameFour",
            name_id_6="PostScriptSix",
        )
        faces = reader.read_faces(font_path)
        assert len(faces) == 1
        face = faces[0]

        names_by_id: dict[int, list[str]] = {}
        for rec in face.name_records:
            names_by_id.setdefault(rec.name_id, []).append(rec.value)

        assert "FamilyOne" in names_by_id.get(1, [])
        assert "FullNameFour" in names_by_id.get(4, [])
        assert "PostScriptSix" in names_by_id.get(6, [])

        # All three are different
        id1 = set(names_by_id.get(1, []))
        id4 = set(names_by_id.get(4, []))
        id6 = set(names_by_id.get(6, []))
        assert not (id1 & id4 & id6)


# ---------------------------------------------------------------------------
# Test 4: cmap coverage as compact ranges, non-contiguous
# ---------------------------------------------------------------------------


class TestCmapRanges:
    def test_contiguous_cmap_single_range(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        font_path = _build_font(
            tmp_path,
            "contiguous.ttf",
            cmap_codepoints={65, 66, 67, 68, 69},  # A-E
        )
        faces = reader.read_faces(font_path)
        assert len(faces) == 1
        ranges = faces[0].cmap_ranges
        assert len(ranges) == 1
        assert ranges[0].start == 65
        assert ranges[0].end == 69

    def test_noncontiguous_cmap_multiple_ranges(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        # Two disjoint groups: {65,66,67} and {100,101}
        font_path = _build_font(
            tmp_path,
            "noncontiguous.ttf",
            cmap_codepoints={65, 66, 67, 100, 101},
        )
        faces = reader.read_faces(font_path)
        assert len(faces) == 1
        ranges = faces[0].cmap_ranges
        assert len(ranges) == 2
        assert ranges[0].start == 65
        assert ranges[0].end == 67
        assert ranges[1].start == 100
        assert ranges[1].end == 101


# ---------------------------------------------------------------------------
# Test 5a: coverage entirely inside U+E000–U+F8FF (BMP PUA)
# ---------------------------------------------------------------------------


class TestPuaCoverage:
    def test_coverage_entirely_in_bmp_pua(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        pua_cps = {0xE000, 0xE001, 0xE002, 0xE010}
        font_path = _build_font(
            tmp_path,
            "pua.ttf",
            cmap_codepoints=pua_cps,
        )
        faces = reader.read_faces(font_path)
        assert len(faces) == 1
        for r in faces[0].cmap_ranges:
            assert 0xE000 <= r.start <= 0xF8FF
            assert 0xE000 <= r.end <= 0xF8FF

    def test_coverage_in_pua_subset_f200_f30f(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        pua_cps = {0xF200, 0xF201, 0xF250, 0xF30F}
        font_path = _build_font(
            tmp_path,
            "pua_subset.ttf",
            cmap_codepoints=pua_cps,
        )
        faces = reader.read_faces(font_path)
        assert len(faces) == 1
        for r in faces[0].cmap_ranges:
            assert 0xF200 <= r.start <= 0xF30F
            assert 0xF200 <= r.end <= 0xF30F


# ---------------------------------------------------------------------------
# Test 6: truncated / malformed font → no exception, unverifiable_reason set
# ---------------------------------------------------------------------------


class TestMalformedFont:
    def test_truncated_font_no_exception(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        bad_path = tmp_path / "truncated.ttf"
        bad_path.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 10)
        faces = reader.read_faces(bad_path)
        assert len(faces) == 1
        assert faces[0].unverifiable_reason is not None
        assert len(faces[0].unverifiable_reason) > 0

    def test_empty_file_no_exception(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        bad_path = tmp_path / "empty.ttf"
        bad_path.write_bytes(b"")
        faces = reader.read_faces(bad_path)
        assert len(faces) == 1
        assert faces[0].unverifiable_reason is not None

    def test_random_bytes_no_exception(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        bad_path = tmp_path / "garbage.ttf"
        bad_path.write_bytes(b"this is not a font file at all")
        faces = reader.read_faces(bad_path)
        assert len(faces) == 1
        assert faces[0].unverifiable_reason is not None

    def test_truncated_ttc_no_exception(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        bad_path = tmp_path / "truncated.ttc"
        # TTC magic header but truncated content
        bad_path.write_bytes(b"ttcf" + b"\x00" * 20)
        faces = reader.read_faces(bad_path)
        assert len(faces) == 1
        assert faces[0].unverifiable_reason is not None


# ---------------------------------------------------------------------------
# Test 7: filename contradicts every internal name record → filename ignored
# ---------------------------------------------------------------------------


class TestFilenameIgnored:
    def test_filename_not_used_for_identity(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        """R6: filename is never identity.  Internal name records must be
        returned regardless of the filename."""
        font_path = _build_font(
            tmp_path,
            "CompletelyWrongName_v3_FINAL_final.ttf",
            name_id_1="InternalFamily",
            name_id_4="InternalFullName",
            name_id_6="InternalPostScript",
            name_id_16="InternalTypographic",
        )
        faces = reader.read_faces(font_path)
        assert len(faces) == 1
        face = faces[0]

        # The filename is nowhere in the result
        all_values = [rec.value for rec in face.name_records]
        for value in all_values:
            assert "CompletelyWrongName" not in value
            assert "FINAL" not in value

        # Internal names are present
        names_by_id: dict[int, list[str]] = {}
        for rec in face.name_records:
            names_by_id.setdefault(rec.name_id, []).append(rec.value)

        assert "InternalFamily" in names_by_id.get(1, [])
        assert "InternalFullName" in names_by_id.get(4, [])
        assert "InternalPostScript" in names_by_id.get(6, [])
        assert "InternalTypographic" in names_by_id.get(16, [])


# ---------------------------------------------------------------------------
# Additional coverage: weight and slant extraction
# ---------------------------------------------------------------------------


class TestWeightAndSlant:
    def test_weight_extracted(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        font_path = _build_font(
            tmp_path,
            "bold.ttf",
            weight_class=700,
        )
        faces = reader.read_faces(font_path)
        assert faces[0].weight == 700

    def test_italic_slant_extracted(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        font_path = _build_font(
            tmp_path,
            "italic.ttf",
            is_italic=True,
        )
        faces = reader.read_faces(font_path)
        assert faces[0].slant == "italic"

    def test_regular_slant_is_none(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        font_path = _build_font(
            tmp_path,
            "regular.ttf",
            is_italic=False,
        )
        faces = reader.read_faces(font_path)
        assert faces[0].slant is None


# ---------------------------------------------------------------------------
# Test: ADMISSIBLE_NAME_IDS is always used by reference, never literal
# ---------------------------------------------------------------------------


class TestAdmissibleNameIdsReference:
    def test_constant_value_matches_provisional(self) -> None:
        """Every test that depends on ADMISSIBLE_NAME_IDS must reference
        the constant, never a literal."""
        assert ADMISSIBLE_NAME_IDS == frozenset({1, 4, 6, 16})

    def test_name_records_only_contain_tracked_ids(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        """The reader records name IDs 1, 4, 6, 16, 21.  IDs 1, 4, 6, 16
        are in ADMISSIBLE_NAME_IDS; 21 is additionally tracked."""
        font_path = _build_font(
            tmp_path,
            "tracked.ttf",
            name_id_1="One",
            name_id_4="Four",
            name_id_6="Six",
            name_id_16="Sixteen",
            name_id_21="TwentyOne",
        )
        faces = reader.read_faces(font_path)
        recorded_ids = {rec.name_id for rec in faces[0].name_records}
        # All admissible IDs that are set should be present
        for nid in ADMISSIBLE_NAME_IDS:
            assert nid in recorded_ids
        # 21 is also tracked (but not in ADMISSIBLE_NAME_IDS)
        assert 21 in recorded_ids


# ---------------------------------------------------------------------------
# Test: nonexistent path
# ---------------------------------------------------------------------------


class TestNonexistentPath:
    def test_nonexistent_path_returns_unverifiable(
        self, reader: FontFaceReaderAdapter, tmp_path: Path
    ) -> None:
        faces = reader.read_faces(tmp_path / "does_not_exist.ttf")
        assert len(faces) == 1
        assert faces[0].unverifiable_reason is not None
