"""Unit tests for the renderability Pydantic models.

Covers:
  8a. report_schema_version is exactly "1.0.0"
  8b. Every top-level block exists when the report is empty
  8c. A Requirement cannot be constructed without track_id and codepoint_ranges
  8d. Every disposition field defaults to null
  8e. Boolean flags default to False
  8f. Enums have exactly the specified members
  8g. ADMISSIBLE_NAME_IDS is the provisional frozenset
"""

from datetime import UTC

import pytest
from pydantic import ValidationError

from src.models.renderability import (
    ADMISSIBLE_NAME_IDS,
    REPORT_SCHEMA_VERSION,
    Attachment,
    AttachmentFace,
    CodepointRange,
    Disposition,
    Environment,
    ProvenanceEntry,
    RenderabilityReport,
    Requirement,
    Style,
    StyleVerdict,
    SubtitleTrack,
    Summary,
    Verdict,
    Warning,
)

# ── 8a. Schema version ────────────────────────────────────────────────


class TestSchemaVersion:
    def test_report_schema_version_is_1_0_0(self) -> None:
        assert REPORT_SCHEMA_VERSION == "1.0.0"

    def test_report_model_default_version(self) -> None:
        report = RenderabilityReport()
        assert report.report_schema_version == "1.0.0"

    def test_report_serialised_version(self) -> None:
        report = RenderabilityReport()
        data = report.model_dump(mode="json")
        assert data["report_schema_version"] == "1.0.0"


# ── 8b. Every top-level block exists when empty ───────────────────────


class TestEmptyReport:
    def test_all_top_level_blocks_present(self) -> None:
        report = RenderabilityReport()
        assert isinstance(report.environment, Environment)
        assert isinstance(report.warnings, list)
        assert isinstance(report.attachments, list)
        assert isinstance(report.subtitle_tracks, list)
        assert isinstance(report.styles, list)
        assert isinstance(report.requirements, list)
        assert isinstance(report.verdicts, list)
        assert isinstance(report.provenance, list)
        assert isinstance(report.summary, Summary)

    def test_empty_report_lists_are_empty(self) -> None:
        report = RenderabilityReport()
        assert report.warnings == []
        assert report.attachments == []
        assert report.subtitle_tracks == []
        assert report.styles == []
        assert report.requirements == []
        assert report.verdicts == []
        assert report.provenance == []

    def test_empty_report_summary_zeros(self) -> None:
        report = RenderabilityReport()
        assert report.summary.total_styles == 0
        assert report.summary.total_requirements == 0
        assert report.summary.renderable == 0
        assert report.summary.not_renderable == 0
        assert report.summary.unverifiable == 0
        assert report.summary.ambiguous == 0


# ── 8c. Requirement mandatory fields ─────────────────────────────────


class TestRequirementValidation:
    def test_requirement_needs_track_id_and_codepoint_ranges(self) -> None:
        # Valid construction
        req = Requirement(
            track_id=0,
            codepoint_ranges=[CodepointRange(start=65, end=90)],
        )
        assert req.track_id == 0
        assert len(req.codepoint_ranges) == 1

    def test_requirement_missing_track_id(self) -> None:
        with pytest.raises(ValidationError):
            Requirement(  # type: ignore[call-arg]
                codepoint_ranges=[CodepointRange(start=65, end=90)],
            )

    def test_requirement_missing_codepoint_ranges(self) -> None:
        with pytest.raises(ValidationError):
            Requirement(  # type: ignore[call-arg]
                track_id=0,
            )

    def test_requirement_codepoints_optional(self) -> None:
        req = Requirement(
            track_id=1,
            codepoint_ranges=[CodepointRange(start=65, end=90)],
        )
        assert req.codepoints is None

    def test_requirement_codepoints_verbose(self) -> None:
        req = Requirement(
            track_id=1,
            codepoint_ranges=[CodepointRange(start=65, end=67)],
            codepoints=[65, 66, 67],
        )
        assert req.codepoints == [65, 66, 67]


# ── 8d. Disposition fields default to null ────────────────────────────


class TestDispositionDefaults:
    def test_style_verdict_disposition_defaults_none(self) -> None:
        sv = StyleVerdict(
            style_name="Default",
            track_id=0,
            verdict=Verdict.AMBIGUOUS,
        )
        assert sv.disposition is None

    def test_disposition_null_in_json(self) -> None:
        sv = StyleVerdict(
            style_name="Default",
            track_id=0,
            verdict=Verdict.NOT_RENDERABLE,
        )
        data = sv.model_dump(mode="json")
        assert data["disposition"] is None


# ── 8e. Boolean flags default to False ────────────────────────────────


class TestRequirementBooleanDefaults:
    def test_all_flags_default_false(self) -> None:
        req = Requirement(
            track_id=0,
            codepoint_ranges=[CodepointRange(start=65, end=90)],
        )
        assert req.shaping_unverified is False
        assert req.missing_style_default is False
        assert req.synthesised_default is False
        assert req.is_pua_only is False


# ── 8f. Enum membership ──────────────────────────────────────────────


class TestEnumMembers:
    def test_verdict_has_exactly_six_members(self) -> None:
        expected = {
            "RENDERABLE_AS_INTENDED",
            "RENDERABLE_SYNTHESISED",
            "RENDERABLE_VIA_FALLBACK",
            "AMBIGUOUS",
            "NOT_RENDERABLE",
            "UNVERIFIABLE",
        }
        assert {m.name for m in Verdict} == expected

    def test_disposition_has_exactly_five_members(self) -> None:
        expected = {
            "PENDING",
            "SUBSTITUTE",
            "LEAVE_AND_REPORT",
            "RETAG_ASS",
            "UNREPAIRABLE_DOCUMENTED",
        }
        assert {m.name for m in Disposition} == expected


# ── 8g. ADMISSIBLE_NAME_IDS ──────────────────────────────────────────


class TestAdmissibleNameIds:
    def test_provisional_value(self) -> None:
        assert ADMISSIBLE_NAME_IDS == frozenset({1, 4, 6, 16})

    def test_is_frozenset(self) -> None:
        assert isinstance(ADMISSIBLE_NAME_IDS, frozenset)


# ── Additional model constraints ─────────────────────────────────────


class TestModelFrozenness:
    def test_report_is_frozen(self) -> None:
        report = RenderabilityReport()
        with pytest.raises(ValidationError):
            report.episode_path = "changed"  # type: ignore[misc]

    def test_requirement_is_frozen(self) -> None:
        req = Requirement(
            track_id=0,
            codepoint_ranges=[],
        )
        with pytest.raises(ValidationError):
            req.track_id = 99  # type: ignore[misc]


class TestAttachmentFaces:
    def test_attachment_carries_faces_array(self) -> None:
        att = Attachment(
            attachment_id=0,
            attachment_filename="test.ttf",
            faces=[
                AttachmentFace(face_index=0),
                AttachmentFace(face_index=1),
            ],
        )
        assert len(att.faces) == 2
        assert att.faces[0].face_index == 0
        assert att.faces[1].face_index == 1

    def test_attachment_empty_faces_default(self) -> None:
        att = Attachment(attachment_id=0, attachment_filename="test.ttf")
        assert att.faces == []


class TestJsonRoundTrip:
    def test_full_report_serialises(self) -> None:
        """A report with data in every block can round-trip through JSON."""
        from datetime import datetime

        report = RenderabilityReport(
            report_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            episode_path="/test.mkv",
            environment=Environment(
                fonttools_version="4.63.0",
                python_version="3.11.15",
                platform="win32",
            ),
            warnings=[Warning(code="W001", message="test warning")],
            attachments=[
                Attachment(
                    attachment_id=0,
                    attachment_filename="font.ttf",
                    faces=[
                        AttachmentFace(
                            face_index=0,
                            cmap_ranges=[CodepointRange(start=65, end=90)],
                            weight=400,
                            slant=None,
                        )
                    ],
                )
            ],
            subtitle_tracks=[SubtitleTrack(track_id=2, codec="ass")],
            styles=[Style(name="Default", font_name="Arial", track_id=2)],
            requirements=[
                Requirement(
                    track_id=2,
                    style_name="Default",
                    font_name="Arial",
                    codepoint_ranges=[CodepointRange(start=65, end=90)],
                )
            ],
            verdicts=[
                StyleVerdict(
                    style_name="Default",
                    track_id=2,
                    verdict=Verdict.RENDERABLE_AS_INTENDED,
                )
            ],
            provenance=[
                ProvenanceEntry(
                    action="created",
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ],
            summary=Summary(total_styles=1, renderable=1),
        )
        data = report.model_dump(mode="json")
        restored = RenderabilityReport.model_validate(data)
        assert restored.report_schema_version == "1.0.0"
        assert len(restored.attachments) == 1
        assert restored.attachments[0].faces[0].weight == 400
