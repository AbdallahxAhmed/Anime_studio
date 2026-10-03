"""Unit tests for the pure renderability engine.

The engine is core logic, so nothing in it is mocked (Constitution X).  Inputs
are plain domain models; the only injected collaborators are a deterministic
clock and an ``Environment`` value.

Covers:
  1. Every verdict branch (as-intended, synthesised, via-fallback, ambiguous,
     not-renderable, unverifiable) and the boundaries between them
  2. libass-grounded ranking, synthesis thresholds, and name matching
  3. PUA-only fonts and PUA requirements
  4. Font collections (multi-face attachments)
  5. Style resolution, including missing-style fallback (E10)
  6. Report assembly: summary, warnings, UTC timestamps, provenance, JSON
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.core import renderability_engine as engine_module
from src.core.renderability_engine import (
    RENDERABLE_VERDICTS,
    RenderabilityEngine,
    face_is_italic,
    face_weight,
    fold_font_name,
    style_distance,
)
from src.models import renderability as models
from src.models.renderability import (
    Attachment,
    AttachmentFace,
    CodepointRange,
    Environment,
    FaceNameRecord,
    ProvenanceEntry,
    RenderabilityReport,
    Requirement,
    Style,
    SubtitleTrack,
    Verdict,
)
from src.models.renderability import Warning as ReportWarning

LATIN = ((0x41, 0x5A), (0x61, 0x7A))
ARABIC = ((0x0621, 0x063A), (0x0641, 0x064A))

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _record(
    name_id: int, value: str, platform: int = 3, encoding: int = 1, lang: int = 0x409
) -> FaceNameRecord:
    return FaceNameRecord(
        name_id=name_id,
        platform_id=platform,
        encoding_id=encoding,
        language_id=lang,
        value=value,
    )


def _ranges(spec: Sequence[tuple[int, int]]) -> list[CodepointRange]:
    return [CodepointRange(start=a, end=b) for a, b in spec]


def _face(
    index: int = 0,
    *,
    family: str | None = "Foo",
    full: str | None = None,
    postscript: str | None = None,
    typographic: str | None = None,
    wws: str | None = None,
    cmap: Sequence[tuple[int, int]] = LATIN,
    weight: int | None = 400,
    slant: str | None = None,
    reason: str | None = None,
) -> AttachmentFace:
    records: list[FaceNameRecord] = []
    if family is not None:
        records.append(_record(1, family))
    if full is not None:
        records.append(_record(4, full))
    if postscript is not None:
        records.append(_record(6, postscript))
    if typographic is not None:
        records.append(_record(16, typographic))
    if wws is not None:
        records.append(_record(21, wws))
    return AttachmentFace(
        face_index=index,
        name_records=records,
        cmap_ranges=_ranges(cmap),
        weight=weight,
        slant=slant,
        unverifiable_reason=reason,
    )


def _broken(index: int = 0, reason: str = "truncated") -> AttachmentFace:
    return AttachmentFace(face_index=index, unverifiable_reason=reason)


def _attachment(
    attachment_id: int, *faces: AttachmentFace, filename: str = "font.ttf"
) -> Attachment:
    return Attachment(
        attachment_id=attachment_id,
        attachment_filename=filename,
        mime_type="font/ttf",
        faces=list(faces),
    )


def _req(
    font: str = "Foo",
    *,
    bold: bool = False,
    italic: bool = False,
    ranges: Sequence[tuple[int, int]] = ((0x41, 0x43),),
    style: str = "Default",
    track: int = 0,
    **flags: bool,
) -> Requirement:
    return Requirement(
        track_id=track,
        style_name=style,
        font_name=font,
        bold=bold,
        italic=italic,
        codepoint_ranges=_ranges(ranges),
        **flags,
    )


def _style(
    name: str = "Default",
    font: str = "Foo",
    *,
    bold: bool = False,
    italic: bool = False,
    track: int = 0,
) -> Style:
    return Style(name=name, font_name=font, bold=bold, italic=italic, track_id=track)


class _Clock:
    """Deterministic UTC clock advancing one second per call."""

    def __init__(self) -> None:
        self._now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


def _evaluate(
    attachments: Sequence[Attachment],
    requirements: Sequence[Requirement],
    styles: Sequence[Style] = (),
    **kwargs: object,
) -> RenderabilityReport:
    return RenderabilityEngine(clock=_Clock()).evaluate(
        episode_path="/lib/ep01.mkv",
        attachments=attachments,
        styles=styles,
        requirements=requirements,
        **kwargs,  # type: ignore[arg-type]
    )


def _verdict(report: RenderabilityReport, index: int = 0) -> Verdict:
    return report.verdicts[index].verdict


def _codes(report: RenderabilityReport) -> list[str]:
    return [w.code for w in report.warnings]


# ---------------------------------------------------------------------------
# RENDERABLE_AS_INTENDED
# ---------------------------------------------------------------------------


class TestAsIntended:
    def test_exact_match_covers_everything(self) -> None:
        report = _evaluate([_attachment(7, _face())], [_req()])
        verdict = report.verdicts[0]
        assert verdict.verdict is Verdict.RENDERABLE_AS_INTENDED
        assert verdict.matched_attachment_id == 7
        assert verdict.matched_face_index == 0
        assert verdict.disposition is None
        assert "covers all 3 required" in verdict.reason

    def test_bold_request_picks_bold_face(self) -> None:
        attachments = [
            _attachment(1, _face(weight=400)),
            _attachment(2, _face(weight=700)),
        ]
        report = _evaluate(attachments, [_req(bold=True)])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.verdicts[0].matched_attachment_id == 2

    def test_regular_request_picks_regular_face(self) -> None:
        attachments = [
            _attachment(1, _face(weight=700)),
            _attachment(2, _face(weight=400)),
        ]
        report = _evaluate(attachments, [_req()])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.verdicts[0].matched_attachment_id == 2

    def test_italic_request_picks_italic_face(self) -> None:
        attachments = [
            _attachment(1, _face()),
            _attachment(2, _face(slant="italic")),
        ]
        report = _evaluate(attachments, [_req(italic=True)])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.verdicts[0].matched_attachment_id == 2

    @pytest.mark.parametrize(
        ("kwargs", "requested"),
        [
            ({"family": "Foo"}, "Foo"),
            ({"family": "Other", "typographic": "Foo"}, "Foo"),
            ({"family": "Other", "full": "Foo Display"}, "Foo Display"),
            ({"family": "Other", "postscript": "Foo-Display"}, "Foo-Display"),
        ],
    )
    def test_admissible_name_ids_match(
        self, kwargs: dict[str, str], requested: str
    ) -> None:
        report = _evaluate([_attachment(1, _face(**kwargs))], [_req(requested)])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_name_id_21_is_never_identity(self) -> None:
        face = _face(family="Other", wws="Foo")
        report = _evaluate([_attachment(1, face)], [_req("Foo")])
        assert _verdict(report) is Verdict.NOT_RENDERABLE

    @pytest.mark.parametrize("requested", ["FOO", "foo", "  Foo  ", "@Foo", "@ foo"])
    def test_name_comparison_is_ascii_case_insensitive_and_trimmed(
        self, requested: str
    ) -> None:
        report = _evaluate([_attachment(1, _face())], [_req(requested)])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_non_ascii_names_are_compared_exactly(self) -> None:
        """libass folds ASCII only, so 'É' and 'é' are different fonts."""
        face = _face(family="Élan")
        assert _verdict(_evaluate([_attachment(1, face)], [_req("Élan")])) is (
            Verdict.RENDERABLE_AS_INTENDED
        )
        assert _verdict(_evaluate([_attachment(1, face)], [_req("élan")])) is (
            Verdict.NOT_RENDERABLE
        )

    def test_filename_is_never_identity(self) -> None:
        """R6: a filename that claims 'Foo' cannot make an unrelated face Foo."""
        attachment = _attachment(1, _face(family="Bar"), filename="Foo.ttf")
        assert _verdict(_evaluate([attachment], [_req("Foo")])) is (
            Verdict.NOT_RENDERABLE
        )
        assert _verdict(_evaluate([attachment], [_req("Bar")])) is (
            Verdict.RENDERABLE_AS_INTENDED
        )

    def test_full_name_match_accepts_heavier_face_than_requested(self) -> None:
        """Naming 'Foo Bold' explicitly asks for that face; it is not a substitute."""
        face = _face(family="Foo", full="Foo Bold", weight=700)
        report = _evaluate([_attachment(1, face)], [_req("Foo Bold", bold=False)])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_full_name_match_accepts_italic_face_when_upright_requested(self) -> None:
        face = _face(family="Foo", full="Foo Italic", slant="italic")
        report = _evaluate([_attachment(1, face)], [_req("Foo Italic")])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_ignorable_codepoints_need_no_glyph(self) -> None:
        ranges = ((0x41, 0x43), (0x200C, 0x200F), (0xAD, 0xAD), (0xFE0F, 0xFE0F))
        report = _evaluate([_attachment(1, _face())], [_req(ranges=ranges)])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_ordinary_space_needs_a_glyph(self) -> None:
        cmap = ((0x41, 0x5A),)
        report = _evaluate(
            [_attachment(1, _face(cmap=cmap))], [_req(ranges=((0x20, 0x20),))]
        )
        # A space is decorative, so its absence degrades to fallback, not failure.
        assert _verdict(report) is Verdict.RENDERABLE_VIA_FALLBACK

    def test_requirement_without_codepoints_checks_only_the_font(self) -> None:
        report = _evaluate([_attachment(1, _face())], [_req(ranges=())])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert "no_required_codepoints" in _codes(report)
        missing = _evaluate([_attachment(1, _face(family="Bar"))], [_req(ranges=())])
        assert _verdict(missing) is Verdict.NOT_RENDERABLE

    def test_name_ids_follow_the_frozen_constant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """W0-C may freeze a different set; the engine reads it at call time."""
        face = _face(family="Other", full="Foo Display", typographic="Typo")
        attachments = [_attachment(1, face)]
        assert _verdict(_evaluate(attachments, [_req("Foo Display")])) is (
            Verdict.RENDERABLE_AS_INTENDED
        )
        monkeypatch.setattr(models, "ADMISSIBLE_NAME_IDS", frozenset({1}))
        assert _verdict(_evaluate(attachments, [_req("Foo Display")])) is (
            Verdict.NOT_RENDERABLE
        )
        assert _verdict(_evaluate(attachments, [_req("Typo")])) is (
            Verdict.NOT_RENDERABLE
        )
        assert _verdict(_evaluate(attachments, [_req("Other")])) is (
            Verdict.RENDERABLE_AS_INTENDED
        )


class TestFrozenNameIdConstant:
    """The W0-C-frozen ``ADMISSIBLE_NAME_IDS`` fully drives identity matching."""

    def test_extra_admissible_id_is_treated_as_a_family_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        face = _face(family="Other", wws="Foo")
        attachments = [_attachment(1, face)]
        assert _verdict(_evaluate(attachments, [_req("Foo")])) is Verdict.NOT_RENDERABLE
        monkeypatch.setattr(models, "ADMISSIBLE_NAME_IDS", frozenset({1, 21}))
        assert _verdict(_evaluate(attachments, [_req("Foo")])) is (
            Verdict.RENDERABLE_AS_INTENDED
        )

    def test_unnamed_face_is_reported(self) -> None:
        report = _evaluate([_attachment(1, _face(family=None))], [_req()])
        assert "face_unnamed" in _codes(report)
        assert _verdict(report) is Verdict.NOT_RENDERABLE


# ---------------------------------------------------------------------------
# RENDERABLE_SYNTHESISED
# ---------------------------------------------------------------------------


class TestSynthesised:
    def test_bold_requested_but_only_regular_attached(self) -> None:
        report = _evaluate([_attachment(1, _face(weight=400))], [_req(bold=True)])
        assert _verdict(report) is Verdict.RENDERABLE_SYNTHESISED
        assert "synthesise bold" in report.verdicts[0].reason
        assert report.requirements[0].synthesised_default is True

    def test_italic_requested_but_only_upright_attached(self) -> None:
        report = _evaluate([_attachment(1, _face())], [_req(italic=True)])
        assert _verdict(report) is Verdict.RENDERABLE_SYNTHESISED
        assert "synthesise italic" in report.verdicts[0].reason

    def test_bold_italic_both_synthesised(self) -> None:
        report = _evaluate([_attachment(1, _face())], [_req(bold=True, italic=True)])
        assert _verdict(report) is Verdict.RENDERABLE_SYNTHESISED
        assert "bold and italic" in report.verdicts[0].reason

    def test_oblique_only_face_is_not_italic_to_libass(self) -> None:
        face = _face(slant="oblique")
        report = _evaluate([_attachment(1, face)], [_req(italic=True)])
        assert _verdict(report) is Verdict.RENDERABLE_SYNTHESISED

    @pytest.mark.parametrize(
        ("face_weight_class", "expected"),
        [
            (249, Verdict.RENDERABLE_SYNTHESISED),
            (250, Verdict.RENDERABLE_AS_INTENDED),
            (200, Verdict.RENDERABLE_SYNTHESISED),
            (300, Verdict.RENDERABLE_AS_INTENDED),
            (500, Verdict.RENDERABLE_AS_INTENDED),
        ],
    )
    def test_regular_request_boundary_against_light_faces(
        self, face_weight_class: int, expected: Verdict
    ) -> None:
        """libass emboldens when requested 400 > face weight + 150."""
        report = _evaluate([_attachment(1, _face(weight=face_weight_class))], [_req()])
        assert _verdict(report) is expected

    @pytest.mark.parametrize(
        ("face_weight_class", "expected"),
        [
            (549, Verdict.RENDERABLE_SYNTHESISED),
            (550, Verdict.RENDERABLE_AS_INTENDED),
            (600, Verdict.RENDERABLE_AS_INTENDED),
            (700, Verdict.RENDERABLE_AS_INTENDED),
            (500, Verdict.RENDERABLE_SYNTHESISED),
        ],
    )
    def test_bold_request_boundary(
        self, face_weight_class: int, expected: Verdict
    ) -> None:
        """libass emboldens when requested 700 > face weight + 150."""
        report = _evaluate(
            [_attachment(1, _face(weight=face_weight_class))], [_req(bold=True)]
        )
        assert _verdict(report) is expected

    def test_legacy_os2_weight_class_is_translated(self) -> None:
        """usWeightClass 7 is legacy 'bold' = 700, so no synthesis is needed."""
        report = _evaluate([_attachment(1, _face(weight=7))], [_req(bold=True)])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_missing_weight_is_assumed_regular_with_a_warning(self) -> None:
        report = _evaluate([_attachment(1, _face(weight=None))], [_req(bold=True)])
        assert _verdict(report) is Verdict.RENDERABLE_SYNTHESISED
        assert "face_weight_unknown" in _codes(report)

    def test_synthesis_with_missing_glyph_still_reports_the_flag(self) -> None:
        ranges = ((0x41, 0x43), (0x266A, 0x266A))
        report = _evaluate([_attachment(1, _face())], [_req(bold=True, ranges=ranges)])
        assert _verdict(report) is Verdict.RENDERABLE_VIA_FALLBACK
        assert report.requirements[0].synthesised_default is True
        assert "synthesise bold" in report.verdicts[0].reason


# ---------------------------------------------------------------------------
# RENDERABLE_VIA_FALLBACK
# ---------------------------------------------------------------------------


class TestViaFallback:
    def test_missing_glyphs_supplied_by_a_sibling_face(self) -> None:
        regular = _face(weight=400, cmap=LATIN)
        bold = _face(weight=700, cmap=LATIN + ARABIC)
        ranges = ((0x41, 0x43), (0x0627, 0x0628))
        report = _evaluate(
            [_attachment(1, regular), _attachment(2, bold)], [_req(ranges=ranges)]
        )
        verdict = report.verdicts[0]
        assert verdict.verdict is Verdict.RENDERABLE_VIA_FALLBACK
        assert verdict.matched_attachment_id == 1  # the face libass picks first
        assert "other faces of the family" in verdict.reason

    def test_decorative_glyphs_in_no_face_fall_back_to_system_fonts(self) -> None:
        ranges = ((0x41, 0x43), (0x266A, 0x266A), (0x2014, 0x2014))
        report = _evaluate([_attachment(1, _face())], [_req(ranges=ranges)])
        assert _verdict(report) is Verdict.RENDERABLE_VIA_FALLBACK
        assert "system fonts" in report.verdicts[0].reason

    def test_only_a_heavier_face_is_a_substitute(self) -> None:
        report = _evaluate([_attachment(1, _face(weight=700))], [_req()])
        assert _verdict(report) is Verdict.RENDERABLE_VIA_FALLBACK
        assert "heavier substitute" in report.verdicts[0].reason

    def test_only_an_italic_face_is_a_substitute_for_upright(self) -> None:
        report = _evaluate([_attachment(1, _face(slant="italic"))], [_req()])
        assert _verdict(report) is Verdict.RENDERABLE_VIA_FALLBACK
        assert "slanted substitute" in report.verdicts[0].reason

    def test_libass_prefers_weight_over_slant(self) -> None:
        """Bold upright is served by Bold Italic, not by faux-bolded Regular."""
        attachments = [
            _attachment(1, _face(weight=400)),
            _attachment(2, _face(weight=700, slant="italic")),
        ]
        report = _evaluate(attachments, [_req(bold=True)])
        assert report.verdicts[0].matched_attachment_id == 2
        assert _verdict(report) is Verdict.RENDERABLE_VIA_FALLBACK

    def test_fallback_glyph_in_pua_covered_by_a_sibling(self) -> None:
        """Font Awesome style: Regular and Solid share a family, split PUA coverage."""
        regular = _face(weight=400, cmap=((0xF000, 0xF0FF),))
        solid = _face(weight=900, cmap=((0xF000, 0xF1FF),))
        report = _evaluate(
            [_attachment(1, regular), _attachment(2, solid)],
            [_req(ranges=((0xF100, 0xF101),))],
        )
        assert _verdict(report) is Verdict.RENDERABLE_VIA_FALLBACK
        assert report.requirements[0].is_pua_only is True


# ---------------------------------------------------------------------------
# NOT_RENDERABLE
# ---------------------------------------------------------------------------


class TestNotRenderable:
    def test_no_attachment_carries_the_font(self) -> None:
        report = _evaluate([_attachment(1, _face(family="Bar"))], [_req("Foo")])
        verdict = report.verdicts[0]
        assert verdict.verdict is Verdict.NOT_RENDERABLE
        assert verdict.matched_face_index is None
        assert verdict.matched_attachment_id is None
        assert "no attached face carries 'Foo'" in verdict.reason

    def test_empty_container(self) -> None:
        report = _evaluate([], [_req()])
        assert _verdict(report) is Verdict.NOT_RENDERABLE
        assert "no_attachments" in _codes(report)

    def test_critical_codepoints_uncovered(self) -> None:
        ranges = ((0x41, 0x43), (0x0627, 0x0628))
        report = _evaluate([_attachment(1, _face())], [_req(ranges=ranges)])
        verdict = report.verdicts[0]
        assert verdict.verdict is Verdict.NOT_RENDERABLE
        assert verdict.matched_attachment_id == 1
        assert "U+0627" in verdict.reason

    def test_digits_are_critical(self) -> None:
        report = _evaluate([_attachment(1, _face())], [_req(ranges=((0x30, 0x39),))])
        assert _verdict(report) is Verdict.NOT_RENDERABLE

    def test_a_different_family_never_rescues_missing_glyphs(self) -> None:
        """libass searches only name-matching faces for a missing glyph."""
        attachments = [
            _attachment(1, _face(family="Foo", cmap=LATIN)),
            _attachment(2, _face(family="Bar", cmap=ARABIC)),
        ]
        report = _evaluate(attachments, [_req(ranges=((0x0627, 0x0628),))])
        assert _verdict(report) is Verdict.NOT_RENDERABLE

    def test_non_font_attachment_without_faces_is_ignored_with_a_warning(self) -> None:
        cover = Attachment(
            attachment_id=9, attachment_filename="cover.jpg", mime_type="image/jpeg"
        )
        report = _evaluate([cover, _attachment(1, _face())], [_req()])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert "attachment_without_faces" in _codes(report)


# ---------------------------------------------------------------------------
# PUA
# ---------------------------------------------------------------------------


class TestPua:
    PUA_FONT = ((0xE000, 0xE0FF),)

    def test_pua_only_font_serves_a_pua_requirement(self) -> None:
        face = _face(family="Icons", cmap=self.PUA_FONT)
        report = _evaluate(
            [_attachment(1, face)], [_req("Icons", ranges=((0xE001, 0xE003),))]
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.requirements[0].is_pua_only is True
        assert "pua_glyph_identity_unverified" in _codes(report)

    def test_pua_only_font_cannot_render_ordinary_text(self) -> None:
        face = _face(family="Icons", cmap=self.PUA_FONT)
        report = _evaluate([_attachment(1, face)], [_req("Icons")])
        assert _verdict(report) is Verdict.NOT_RENDERABLE
        assert report.requirements[0].is_pua_only is False

    def test_pua_codepoints_missing_from_the_named_font_are_not_renderable(
        self,
    ) -> None:
        attachments = [
            _attachment(1, _face(family="Icons", cmap=((0xE000, 0xE00F),))),
            _attachment(2, _face(family="Other", cmap=((0xE100, 0xE1FF),))),
        ]
        report = _evaluate(attachments, [_req("Icons", ranges=((0xE100, 0xE101),))])
        # Another family's glyph at the same codepoint is a different glyph.
        assert _verdict(report) is Verdict.NOT_RENDERABLE

    def test_supplementary_pua_planes(self) -> None:
        face = _face(family="Icons", cmap=((0xF0000, 0xF00FF), (0x100000, 0x1000FF)))
        report = _evaluate(
            [_attachment(1, face)],
            [_req("Icons", ranges=((0xF0001, 0xF0002), (0x100001, 0x100001)))],
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.requirements[0].is_pua_only is True

    def test_mixed_requirement_is_not_pua_only(self) -> None:
        face = _face(family="Icons", cmap=LATIN + self.PUA_FONT)
        report = _evaluate(
            [_attachment(1, face)],
            [_req("Icons", ranges=((0x41, 0x43), (0xE001, 0xE001)))],
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.requirements[0].is_pua_only is False

    def test_false_pua_claim_is_corrected_and_reported(self) -> None:
        report = _evaluate([_attachment(1, _face())], [_req(is_pua_only=True)])
        assert report.requirements[0].is_pua_only is False
        assert "requirement_flag_corrected" in _codes(report)


# ---------------------------------------------------------------------------
# Font collections (.ttc = one attachment, several faces)
# ---------------------------------------------------------------------------


class TestCollections:
    def _collection(self) -> Attachment:
        return _attachment(
            3,
            _face(0, family="Foo", weight=400),
            _face(1, family="Foo", weight=700),
            _face(2, family="Foo", weight=400, slant="italic"),
            _face(3, family="Bar", weight=400, cmap=ARABIC),
            filename="Foo.ttc",
        )

    def test_bold_request_selects_the_bold_face_of_the_collection(self) -> None:
        report = _evaluate([self._collection()], [_req(bold=True)])
        verdict = report.verdicts[0]
        assert verdict.verdict is Verdict.RENDERABLE_AS_INTENDED
        assert (verdict.matched_attachment_id, verdict.matched_face_index) == (3, 1)

    def test_italic_request_selects_the_italic_face(self) -> None:
        report = _evaluate([self._collection()], [_req(italic=True)])
        assert report.verdicts[0].matched_face_index == 2

    def test_a_later_family_in_the_collection_is_reachable(self) -> None:
        report = _evaluate(
            [self._collection()], [_req("Bar", ranges=((0x0627, 0x0628),))]
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.verdicts[0].matched_face_index == 3

    def test_unreadable_face_inside_a_collection_only_affects_its_own_name(
        self,
    ) -> None:
        collection = _attachment(
            4, _face(0, family="Foo"), _broken(1, "name table missing")
        )
        report = _evaluate([collection], [_req("Foo"), _req("Baz")])
        assert _verdict(report, 0) is Verdict.RENDERABLE_AS_INTENDED
        assert _verdict(report, 1) is Verdict.UNVERIFIABLE
        assert "face_unverifiable" in _codes(report)


# ---------------------------------------------------------------------------
# AMBIGUOUS
# ---------------------------------------------------------------------------


class TestAmbiguous:
    def test_tied_faces_with_different_outcomes(self) -> None:
        latin_only = _face(cmap=LATIN)
        with_arabic = _face(cmap=LATIN + ARABIC)
        ranges = ((0x41, 0x43), (0x0627, 0x0628))
        report = _evaluate(
            [_attachment(1, latin_only), _attachment(2, with_arabic)],
            [_req(ranges=ranges)],
        )
        verdict = report.verdicts[0]
        assert verdict.verdict is Verdict.AMBIGUOUS
        assert verdict.matched_face_index is None
        assert verdict.matched_attachment_id is None
        assert "attachment 1 face 0 -> renderable_via_fallback" in verdict.reason
        assert "attachment 2 face 0 -> renderable_as_intended" in verdict.reason
        assert report.summary.ambiguous == 1

    def test_tied_faces_that_agree_are_not_ambiguous(self) -> None:
        report = _evaluate([_attachment(1, _face()), _attachment(2, _face())], [_req()])
        verdict = report.verdicts[0]
        assert verdict.verdict is Verdict.RENDERABLE_AS_INTENDED
        assert verdict.matched_attachment_id == 1  # first in attachment order
        assert "tied_candidates" in _codes(report)

    def test_a_clear_winner_is_not_a_tie(self) -> None:
        attachments = [
            _attachment(1, _face(weight=400)),
            _attachment(2, _face(weight=700)),
        ]
        report = _evaluate(attachments, [_req()])
        assert "tied_candidates" not in _codes(report)
        assert report.verdicts[0].matched_attachment_id == 1

    def test_tie_between_family_match_and_full_name_match(self) -> None:
        """A full-name match scores 0, as does an exact family match."""
        family_face = _face(family="Foo", full="Foo Regular", cmap=LATIN)
        named_face = _face(family="FooAlt", full="Foo", cmap=LATIN + ARABIC)
        ranges = ((0x41, 0x43), (0x0627, 0x0627))
        report = _evaluate(
            [_attachment(1, family_face), _attachment(2, named_face)],
            [_req("Foo", ranges=ranges)],
        )
        # Only the family face matches 'Foo' by family; the other by full name.
        assert _verdict(report) is Verdict.AMBIGUOUS


# ---------------------------------------------------------------------------
# UNVERIFIABLE
# ---------------------------------------------------------------------------


class TestUnverifiable:
    def test_only_an_unreadable_face_is_attached(self) -> None:
        report = _evaluate([_attachment(1, _broken())], [_req()])
        verdict = report.verdicts[0]
        assert verdict.verdict is Verdict.UNVERIFIABLE
        assert "unreadable" in verdict.reason
        assert "face_unverifiable" in _codes(report)

    def test_same_name_unreadable_face_is_called_out(self) -> None:
        partial = AttachmentFace(
            face_index=0,
            name_records=[_record(1, "Foo")],
            unverifiable_reason="cmap unreadable",
        )
        report = _evaluate([_attachment(1, partial)], [_req("Foo")])
        assert _verdict(report) is Verdict.UNVERIFIABLE
        assert "carry the name 'Foo'" in report.verdicts[0].reason

    def test_absence_cannot_be_proven_while_something_is_unreadable(self) -> None:
        attachments = [_attachment(1, _face(family="Bar")), _attachment(2, _broken())]
        report = _evaluate(attachments, [_req("Foo")])
        assert _verdict(report) is Verdict.UNVERIFIABLE

    def test_unrelated_corruption_does_not_poison_a_verified_match(self) -> None:
        attachments = [_attachment(1, _face()), _attachment(2, _broken())]
        report = _evaluate(attachments, [_req("Foo")])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert "face_unverifiable" in _codes(report)

    def test_unreadable_face_with_the_requested_name_blocks_an_imperfect_verdict(
        self,
    ) -> None:
        partial = AttachmentFace(
            face_index=0,
            name_records=[_record(1, "Foo")],
            unverifiable_reason="cmap unreadable",
        )
        attachments = [_attachment(1, _face(weight=400)), _attachment(2, partial)]
        report = _evaluate(attachments, [_req(bold=True)])
        assert _verdict(report) is Verdict.UNVERIFIABLE
        assert "could change the outcome" in report.verdicts[0].reason

    def test_unreadable_same_name_face_cannot_beat_a_perfect_match(self) -> None:
        partial = AttachmentFace(
            face_index=0,
            name_records=[_record(1, "Foo")],
            unverifiable_reason="cmap unreadable",
        )
        attachments = [_attachment(1, _face(weight=700)), _attachment(2, partial)]
        report = _evaluate(attachments, [_req(bold=True)])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_malformed_cmap_ranges_make_the_face_unreadable(self) -> None:
        face = AttachmentFace(
            face_index=0,
            name_records=[_record(1, "Foo")],
            cmap_ranges=[CodepointRange(start=9, end=2)],
            weight=400,
        )
        report = _evaluate([_attachment(1, face)], [_req()])
        assert _verdict(report) is Verdict.UNVERIFIABLE
        assert "malformed cmap ranges" in " ".join(w.detail for w in report.warnings)

    @pytest.mark.parametrize(
        "bad_ranges",
        [[(10, 2)], [(0, 0x110000)]],
    )
    def test_malformed_subtitle_ranges(self, bad_ranges: list[tuple[int, int]]) -> None:
        requirement = Requirement(
            track_id=0,
            style_name="Default",
            font_name="Foo",
            codepoint_ranges=_ranges(bad_ranges),
        )
        report = _evaluate([_attachment(1, _face())], [requirement])
        assert _verdict(report) is Verdict.UNVERIFIABLE
        assert "invalid_codepoint_range" in _codes(report)

    def test_requirement_naming_nothing_is_unverifiable(self) -> None:
        requirement = Requirement(track_id=0, codepoint_ranges=_ranges(((0x41, 0x41),)))
        report = _evaluate([_attachment(1, _face())], [requirement])
        assert _verdict(report) is Verdict.UNVERIFIABLE
        assert "requirement_unidentified" in _codes(report)

    def test_style_without_a_style_block_cannot_supply_a_font(self) -> None:
        requirement = Requirement(
            track_id=0,
            style_name="Default",
            codepoint_ranges=_ranges(((0x41, 0x41),)),
        )
        report = _evaluate([_attachment(1, _face())], [requirement])
        assert _verdict(report) is Verdict.UNVERIFIABLE


# ---------------------------------------------------------------------------
# Style resolution and missing-style fallback (E10)
# ---------------------------------------------------------------------------


class TestStyleResolution:
    def test_missing_style_falls_back_to_the_default_style(self) -> None:
        report = _evaluate(
            [_attachment(1, _face(family="Foo"))],
            [_req("", style="Gone")],
            styles=[_style("Default", "Foo")],
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.requirements[0].missing_style_default is True
        assert "missing_style_default" in _codes(report)
        detail = next(
            w.detail for w in report.warnings if w.code == "missing_style_default"
        )
        assert "falls back to style 'Default'" in detail

    def test_missing_style_without_default_uses_the_builtin_arial(self) -> None:
        styles = [_style("Other", "Foo")]
        with_arial = _evaluate(
            [_attachment(1, _face(family="Arial"))],
            [_req("", style="Gone")],
            styles=styles,
        )
        assert _verdict(with_arial) is Verdict.RENDERABLE_AS_INTENDED
        assert "built-in default font (Arial)" in next(
            w.detail for w in with_arial.warnings if w.code == "missing_style_default"
        )
        without_arial = _evaluate(
            [_attachment(1, _face(family="Foo"))],
            [_req("", style="Gone")],
            styles=styles,
        )
        assert _verdict(without_arial) is Verdict.NOT_RENDERABLE

    @pytest.mark.parametrize("name", ["Default", "default", "DEFAULT", "*Default"])
    def test_default_style_matches_case_insensitively(self, name: str) -> None:
        report = _evaluate(
            [_attachment(1, _face())], [_req("", style=name)], styles=[_style()]
        )
        assert report.requirements[0].missing_style_default is False

    def test_other_style_names_are_case_sensitive(self) -> None:
        report = _evaluate(
            [_attachment(1, _face())],
            [_req("", style="sign")],
            styles=[_style("Default", "Foo"), _style("Sign", "Bar")],
        )
        assert report.requirements[0].missing_style_default is True

    def test_last_declaration_of_a_style_wins(self) -> None:
        report = _evaluate(
            [_attachment(1, _face(family="B"))],
            [_req("", style="S")],
            styles=[_style("S", "A"), _style("S", "B")],
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_empty_font_inherits_weight_and_slant_from_the_style(self) -> None:
        attachments = [
            _attachment(1, _face(weight=400)),
            _attachment(2, _face(weight=700, slant="italic")),
        ]
        report = _evaluate(
            attachments,
            [_req("", style="Default")],
            styles=[_style("Default", "Foo", bold=True, italic=True)],
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.verdicts[0].matched_attachment_id == 2

    def test_explicit_font_overrides_the_style_font(self) -> None:
        report = _evaluate(
            [_attachment(1, _face(family="Bar"))],
            [_req("Bar", style="Default")],
            styles=[_style("Default", "Foo")],
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED

    def test_explicit_font_with_a_missing_style_is_still_flagged(self) -> None:
        report = _evaluate(
            [_attachment(1, _face())],
            [_req("Foo", style="Gone")],
            styles=[_style("Default", "Foo")],
        )
        assert report.requirements[0].missing_style_default is True

    def test_no_style_block_means_no_missing_style_claim(self) -> None:
        report = _evaluate([_attachment(1, _face())], [_req("Foo", style="Anything")])
        assert report.requirements[0].missing_style_default is False

    def test_styles_are_scoped_per_track(self) -> None:
        styles = [_style("Default", "Foo", track=0), _style("Default", "Bar", track=1)]
        report = _evaluate(
            [_attachment(1, _face(family="Bar"))],
            [_req("", style="Default", track=1)],
            styles=styles,
        )
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED


# ---------------------------------------------------------------------------
# Shaping (E13)
# ---------------------------------------------------------------------------


class TestShaping:
    def test_complex_script_is_flagged_without_changing_the_verdict(self) -> None:
        face = _face(cmap=ARABIC)
        report = _evaluate([_attachment(1, face)], [_req(ranges=((0x0627, 0x0628),))])
        assert _verdict(report) is Verdict.RENDERABLE_AS_INTENDED
        assert report.requirements[0].shaping_unverified is True
        assert "shaping_unverified" in _codes(report)

    def test_simple_script_is_not_flagged(self) -> None:
        report = _evaluate([_attachment(1, _face())], [_req()])
        assert report.requirements[0].shaping_unverified is False
        assert "shaping_unverified" not in _codes(report)

    def test_input_flag_is_preserved(self) -> None:
        report = _evaluate([_attachment(1, _face())], [_req(shaping_unverified=True)])
        assert report.requirements[0].shaping_unverified is True


# ---------------------------------------------------------------------------
# Ranking primitives
# ---------------------------------------------------------------------------


class TestPrimitives:
    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            (None, 400),
            (0, 400),
            (1, 100),
            (4, 350),
            (5, 400),
            (6, 600),
            (7, 700),
            (9, 900),
            (10, 10),
            (400, 400),
            (550, 550),
            (950, 950),
        ],
    )
    def test_face_weight(self, declared: int | None, expected: int) -> None:
        assert face_weight(_face(weight=declared)) == expected

    def test_face_is_italic_reads_only_the_italic_flag(self) -> None:
        assert face_is_italic(_face(slant="italic"))
        assert not face_is_italic(_face(slant="oblique"))
        assert not face_is_italic(_face(slant=None))

    @pytest.mark.parametrize(
        ("face_w", "face_i", "req_w", "req_i", "expected"),
        [
            (400, False, 400, False, 0),
            (700, False, 700, False, 0),
            (400, False, 400, True, 1),  # italic requested, face upright
            (400, True, 400, False, 4),  # upright requested, face italic
            (400, False, 700, False, 51),  # faux-bold offset: |520-700|*73//256
            (700, False, 400, False, 85),  # |700-400|*73//256
            (550, False, 700, False, 42),  # 700 > 550+150 is false: |550-700|*73//256
        ],
    )
    def test_style_distance_matches_libass(
        self, face_w: int, face_i: bool, req_w: int, req_i: bool, expected: int
    ) -> None:
        assert style_distance(face_w, face_i, req_w, req_i) == expected

    @pytest.mark.parametrize(
        ("raw", "folded"),
        [
            ("Arial", "arial"),
            ("  Arial ", "arial"),
            ("@Arial", "arial"),
            ("@ Arial", "arial"),
            ("ÀRIAL", "Àrial"),
        ],
    )
    def test_fold_font_name(self, raw: str, folded: str) -> None:
        assert fold_font_name(raw) == folded


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


class TestReportAssembly:
    def _mixed_report(self) -> RenderabilityReport:
        attachments = [
            _attachment(1, _face(family="Foo", weight=400)),
            _attachment(2, _broken()),
        ]
        requirements = [
            _req("Foo"),  # as intended
            _req("Foo", bold=True, style="Bold"),  # synthesised
            _req("Foo", ranges=((0x266A, 0x266A),)),  # via fallback
            _req("Nope", style="Sign"),  # unverifiable (unreadable face present)
            _req("Foo", ranges=((0x0627, 0x0627),), style="Ar"),  # not renderable
        ]
        return _evaluate(
            attachments,
            requirements,
            styles=[_style("Default", "Foo"), _style("Bold", "Foo", bold=True)],
        )

    def test_one_verdict_per_requirement_in_order(self) -> None:
        report = self._mixed_report()
        assert [v.verdict for v in report.verdicts] == [
            Verdict.RENDERABLE_AS_INTENDED,
            Verdict.RENDERABLE_SYNTHESISED,
            Verdict.RENDERABLE_VIA_FALLBACK,
            Verdict.UNVERIFIABLE,
            Verdict.NOT_RENDERABLE,
        ]
        assert [v.style_name for v in report.verdicts] == [
            "Default",
            "Bold",
            "Default",
            "Sign",
            "Ar",
        ]

    def test_summary_counts(self) -> None:
        summary = self._mixed_report().summary
        assert summary.total_styles == 2
        assert summary.total_requirements == 5
        assert summary.renderable == 3
        assert summary.not_renderable == 1
        assert summary.unverifiable == 1
        assert summary.ambiguous == 0
        assert (
            summary.renderable
            + summary.not_renderable
            + summary.unverifiable
            + summary.ambiguous
            == summary.total_requirements
        )

    def test_inputs_are_echoed_as_facts(self) -> None:
        tracks = [SubtitleTrack(track_id=0, codec="ASS", language="ara")]
        attachments = [_attachment(1, _face())]
        styles = [_style()]
        report = _evaluate(attachments, [_req()], styles=styles, subtitle_tracks=tracks)
        assert report.episode_path == "/lib/ep01.mkv"
        assert report.attachments == attachments
        assert report.styles == styles
        assert report.subtitle_tracks == tracks
        assert report.report_schema_version == "1.0.0"

    def test_every_disposition_is_none(self) -> None:
        assert all(v.disposition is None for v in self._mixed_report().verdicts)

    def test_timestamps_are_utc_and_ordered(self) -> None:
        report = self._mixed_report()
        assert report.report_timestamp is not None
        assert report.report_timestamp.utcoffset() == timedelta(0)
        stamps = [p.timestamp for p in report.provenance]
        assert all(s.utcoffset() == timedelta(0) for s in stamps)
        assert stamps == sorted(stamps)
        assert report.report_timestamp >= stamps[-1]
        assert report.model_dump(mode="json")["report_timestamp"].endswith("Z")

    def test_provenance_audit_trail(self) -> None:
        report = self._mixed_report()
        actions = [p.action for p in report.provenance]
        assert actions[0] == "analysis_started"
        assert actions[-1] == "analysis_completed"
        assert actions.count("requirement_evaluated") == 5
        decisions = [
            p.detail for p in report.provenance if p.action == "requirement_evaluated"
        ]
        assert "rule=exact" in decisions[0]
        assert "rule=synthesised" in decisions[1]
        assert "rule=fallback_glyphs" in decisions[2]
        assert "rule=unreadable_faces" in decisions[3]
        assert "rule=critical_glyphs_uncovered" in decisions[4]
        assert "admissible_name_ids=[1, 4, 6, 16]" in report.provenance[0].detail

    def test_non_utc_clock_is_normalised(self) -> None:
        cairo = timezone(timedelta(hours=3))
        engine = RenderabilityEngine(
            clock=lambda: datetime(2026, 10, 1, 15, 0, tzinfo=cairo)
        )
        report = engine.evaluate(requirements=[_req()])
        assert report.report_timestamp == datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
        assert report.report_timestamp.utcoffset() == timedelta(0)

    def test_naive_clock_is_rejected(self) -> None:
        engine = RenderabilityEngine(clock=lambda: datetime(2026, 10, 1, 12, 0))
        with pytest.raises(ValueError, match="timezone-aware"):
            engine.evaluate(requirements=[_req()])

    def test_default_clock_is_utc(self) -> None:
        report = RenderabilityEngine().evaluate(requirements=[_req()])
        assert report.report_timestamp is not None
        assert report.report_timestamp.utcoffset() == timedelta(0)

    def test_environment_is_recorded_not_captured(self) -> None:
        env = Environment(
            fonttools_version="4.63.0", python_version="3.11", platform="x"
        )
        engine = RenderabilityEngine(clock=_Clock(), environment=env)
        assert engine.evaluate().environment == env
        assert (
            RenderabilityEngine(clock=_Clock()).evaluate().environment == Environment()
        )

    def test_upstream_warnings_and_provenance_come_first(self) -> None:
        upstream_warning = ReportWarning(code="from_extractor", message="m", detail="d")
        upstream_prov = ProvenanceEntry(
            action="subtitle_parsed",
            timestamp=datetime(2026, 10, 1, 11, 0, tzinfo=UTC),
            detail="lines=10",
        )
        report = _evaluate(
            [_attachment(1, _face())],
            [_req()],
            warnings=[upstream_warning],
            provenance=[upstream_prov],
        )
        assert report.warnings[0] == upstream_warning
        assert report.provenance[0] == upstream_prov
        assert report.provenance[1].action == "analysis_started"

    def test_identical_warnings_are_deduplicated(self) -> None:
        report = _evaluate(
            [_attachment(1, _face(weight=None))], [_req(), _req(style="Other")]
        )
        assert _codes(report).count("face_weight_unknown") == 1

    def test_empty_input_yields_a_complete_empty_report(self) -> None:
        report = RenderabilityEngine(clock=_Clock()).evaluate()
        assert report.verdicts == []
        assert report.summary.total_requirements == 0
        assert "no_attachments" in _codes(report)
        assert report.provenance[0].action == "analysis_started"

    def test_report_round_trips_through_json(self) -> None:
        report = self._mixed_report()
        payload = report.model_dump_json()
        assert RenderabilityReport.model_validate_json(payload) == report

    def test_inputs_are_not_mutated(self) -> None:
        requirement = _req(is_pua_only=True)
        attachments = [_attachment(1, _face())]
        before = (requirement.model_copy(), [a.model_copy() for a in attachments])
        report = _evaluate(attachments, [requirement])
        assert requirement == before[0]
        assert attachments == before[1]
        assert report.requirements[0] is not requirement

    def test_duplicate_attachment_ids_are_reported(self) -> None:
        report = _evaluate([_attachment(1, _face()), _attachment(1, _face())], [_req()])
        assert "duplicate_attachment_id" in _codes(report)


# ---------------------------------------------------------------------------
# Invariants over a grid of inputs
# ---------------------------------------------------------------------------


class TestInvariants:
    FACES = {
        "regular": _face(weight=400),
        "bold": _face(weight=700),
        "italic": _face(slant="italic"),
        "arabic": _face(cmap=LATIN + ARABIC),
        "other_family": _face(family="Bar"),
        "broken": _broken(),
        "pua": _face(cmap=((0xE000, 0xE0FF),)),
    }
    REQUESTS = [
        {"font": "Foo"},
        {"font": "Foo", "bold": True},
        {"font": "Foo", "italic": True},
        {"font": "Foo", "bold": True, "italic": True},
        {"font": "Foo", "ranges": ((0x0627, 0x0628),)},
        {"font": "Foo", "ranges": ((0xE001, 0xE002),)},
        {"font": "Bar"},
        {"font": "Missing"},
    ]

    @pytest.mark.parametrize(
        "names",
        [
            ["regular"],
            ["regular", "bold"],
            ["regular", "bold", "italic"],
            ["regular", "arabic"],
            ["broken"],
            ["regular", "broken"],
            ["other_family", "pua"],
            ["pua", "regular", "arabic", "broken"],
            [],
        ],
    )
    def test_every_requirement_gets_exactly_one_known_verdict(
        self, names: list[str]
    ) -> None:
        attachments = [
            _attachment(i, self.FACES[name]) for i, name in enumerate(names, start=1)
        ]
        requirements = [_req(**request) for request in self.REQUESTS]  # type: ignore[arg-type]
        report = _evaluate(attachments, requirements)

        assert len(report.verdicts) == len(requirements)
        assert all(isinstance(v.verdict, Verdict) for v in report.verdicts)
        summary = report.summary
        assert (
            summary.renderable
            + summary.not_renderable
            + summary.unverifiable
            + summary.ambiguous
            == summary.total_requirements
            == len(requirements)
        )
        assert summary.renderable == sum(
            v.verdict in RENDERABLE_VERDICTS for v in report.verdicts
        )
        for verdict in report.verdicts:
            matched = (verdict.matched_face_index, verdict.matched_attachment_id)
            if verdict.verdict in (Verdict.AMBIGUOUS, Verdict.NOT_RENDERABLE) and (
                "no attached face" in verdict.reason
            ):
                assert matched == (None, None)
            assert verdict.reason  # every verdict explains itself

    def test_engine_is_deterministic(self) -> None:
        attachments = [_attachment(1, _face()), _attachment(2, _face(weight=700))]
        requirements = [_req(), _req(bold=True)]
        first = _evaluate(attachments, requirements)
        second = _evaluate(attachments, requirements)
        assert first == second

    def test_verdict_module_exports_are_consistent(self) -> None:
        assert RENDERABLE_VERDICTS == {
            Verdict.RENDERABLE_AS_INTENDED,
            Verdict.RENDERABLE_SYNTHESISED,
            Verdict.RENDERABLE_VIA_FALLBACK,
        }
        assert engine_module.BOLD_WEIGHT == 700
        assert engine_module.REGULAR_WEIGHT == 400
