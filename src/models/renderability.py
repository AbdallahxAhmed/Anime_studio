"""Renderability report data models (Wave 0, specification revision 1.1).

**Schema stability contract**: the field names, types, and enum members
defined here form an API surface.  Any rename, type change, or member
removal is a **breaking change** and MUST be accompanied by a
``report_schema_version`` bump.

This module is **pure data** (Constitution Principle I):
  - No imports from elsewhere in this project.
  - No filesystem, network, or fontTools access.
  - No I/O of any kind.

Behavioural rules enforced by design:
  R5  Attachment presence is never evidence of resolution.
      → ``AttachmentFace`` carries only identity facts, not verdicts.
  R6  Filenames are never identity; identity comes from name records.
      → ``attachment_filename`` is a label, not an identity key.
  R7  Facts and dispositions are separate.
      → Dispositions live in ``StyleVerdict``, facts in requirement /
        attachment / face models.
  R8  Every timestamp is UTC ISO-8601.
      → ``report_timestamp`` and provenance timestamps are
        ``datetime`` with a docstring mandate for UTC.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

REPORT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
"""Semantic version of the renderability report schema."""

ADMISSIBLE_NAME_IDS: frozenset[int] = frozenset({1, 4, 6, 16})
"""Name-table IDs that *may* be used for font-face identity matching.

# TODO(W0-C): The final value of this constant is frozen by the libass
# name-matching experiment in task W0-C.  The provisional set {1, 4, 6, 16}
# is based on documented libass behaviour and MUST be validated against
# empirical evidence before the schema is stabilised.
"""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Verdict(str, Enum):
    """Renderability verdict for one style–requirement pair.

    Exactly six members; adding or removing a member is a breaking change.
    """

    RENDERABLE_AS_INTENDED = "renderable_as_intended"
    RENDERABLE_SYNTHESISED = "renderable_synthesised"
    RENDERABLE_VIA_FALLBACK = "renderable_via_fallback"
    AMBIGUOUS = "ambiguous"
    NOT_RENDERABLE = "not_renderable"
    UNVERIFIABLE = "unverifiable"


class Disposition(str, Enum):
    """Repair disposition, reserved for later waves.

    Exactly five members; adding or removing a member is a breaking change.
    All disposition fields in W0 reports are ``None``.
    """

    PENDING = "pending"
    SUBSTITUTE = "substitute"
    LEAVE_AND_REPORT = "leave_and_report"
    RETAG_ASS = "retag_ass"
    UNREPAIRABLE_DOCUMENTED = "unrepairable_documented"


# ---------------------------------------------------------------------------
# Sub-models: face and attachment facts
# ---------------------------------------------------------------------------


class FaceNameRecord(BaseModel):
    """A single decoded OpenType name record from a font face."""

    model_config = ConfigDict(frozen=True)

    name_id: int = Field(ge=0)
    platform_id: int = Field(ge=0)
    encoding_id: int = Field(ge=0)
    language_id: int = Field(ge=0)
    value: str


class CodepointRange(BaseModel):
    """An inclusive range of Unicode codepoints ``[start, end]``."""

    model_config = ConfigDict(frozen=True)

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class AttachmentFace(BaseModel):
    """One font face extracted from an MKV attachment.

    Only carries identity facts (R5, R6): name records, cmap coverage,
    weight/slant declarations.  Never carries a verdict.
    """

    model_config = ConfigDict(frozen=True)

    face_index: int = Field(ge=0)
    name_records: list[FaceNameRecord] = Field(default_factory=list)
    cmap_ranges: list[CodepointRange] = Field(default_factory=list)
    weight: int | None = None
    slant: str | None = None
    unverifiable_reason: str | None = None


class Attachment(BaseModel):
    """One font attachment from the MKV container.

    ``attachment_filename`` is a container label, never an identity key (R6).
    ``faces`` carries the actual identity facts for each face in the file.
    """

    model_config = ConfigDict(frozen=True)

    attachment_id: int = Field(ge=0)
    attachment_filename: str
    mime_type: str = ""
    faces: list[AttachmentFace] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-models: subtitle metadata
# ---------------------------------------------------------------------------


class SubtitleTrack(BaseModel):
    """Metadata for one subtitle track in the container."""

    model_config = ConfigDict(frozen=True)

    track_id: int = Field(ge=0)
    codec: str = ""
    language: str = ""
    is_default: bool = False


class Style(BaseModel):
    """One ASS style declaration."""

    model_config = ConfigDict(frozen=True)

    name: str
    font_name: str
    bold: bool = False
    italic: bool = False
    track_id: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Sub-models: requirements and verdicts
# ---------------------------------------------------------------------------


class Requirement(BaseModel):
    """A font-rendering requirement derived from subtitle content.

    ``track_id`` and ``codepoint_ranges`` are mandatory; the expanded
    ``codepoints`` list is optional and populated only in verbose mode.
    """

    model_config = ConfigDict(frozen=True)

    track_id: int = Field(ge=0)
    style_name: str = ""
    font_name: str = ""
    bold: bool = False
    italic: bool = False
    codepoint_ranges: list[CodepointRange]
    codepoints: list[int] | None = None

    # Boolean flags, each defaulting to False, documented with the rule
    # that sets it.
    shaping_unverified: bool = Field(
        default=False,
        description="E13: cmap presence is not proof of correct shaping.",
    )
    missing_style_default: bool = Field(
        default=False,
        description=(
            "E10: a dialogue line references a style absent from the style block."
        ),
    )
    synthesised_default: bool = Field(
        default=False,
        description=(
            "E14: the requested weight or slant was synthesised by the "
            "renderer rather than provided by the font."
        ),
    )
    is_pua_only: bool = Field(
        default=False,
        description=(
            "Coverage lies entirely in Unicode private-use areas "
            "(U+E000–U+F8FF, U+F0000–U+FFFFD, U+100000–U+10FFFD)."
        ),
    )


class StyleVerdict(BaseModel):
    """The verdict for one style–requirement pair.

    Facts (requirement reference, matched face) and disposition are kept
    structurally separate (R7).  In Wave 0, ``disposition`` is always
    ``None``.
    """

    model_config = ConfigDict(frozen=True)

    style_name: str
    track_id: int = Field(ge=0)
    verdict: Verdict
    matched_face_index: int | None = None
    matched_attachment_id: int | None = None
    disposition: Disposition | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Sub-models: provenance, environment, summary
# ---------------------------------------------------------------------------


class Environment(BaseModel):
    """Captured runtime environment at report time."""

    model_config = ConfigDict(frozen=True)

    fonttools_version: str = ""
    python_version: str = ""
    platform: str = ""


class ProvenanceEntry(BaseModel):
    """One provenance record for audit traceability.

    All timestamps MUST be UTC ISO-8601 (R8).
    """

    model_config = ConfigDict(frozen=True)

    action: str
    timestamp: datetime
    detail: str = ""


class Warning(BaseModel):
    """A non-fatal diagnostic emitted during analysis."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    detail: str = ""


class Summary(BaseModel):
    """Aggregate counts from the verdict computation."""

    model_config = ConfigDict(frozen=True)

    total_styles: int = Field(default=0, ge=0)
    total_requirements: int = Field(default=0, ge=0)
    renderable: int = Field(default=0, ge=0)
    not_renderable: int = Field(default=0, ge=0)
    unverifiable: int = Field(default=0, ge=0)
    ambiguous: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Report root
# ---------------------------------------------------------------------------


class RenderabilityReport(BaseModel):
    """Root model of the renderability report.

    All top-level blocks are present even when empty, so consumers
    never need to handle ``None`` at the block level.

    ``report_schema_version`` is a literal ``"1.0.0"`` and MUST be
    bumped on any breaking schema change.

    ``report_timestamp`` MUST be UTC ISO-8601 (R8).
    """

    model_config = ConfigDict(frozen=True)

    report_schema_version: Literal["1.0.0"] = REPORT_SCHEMA_VERSION
    report_timestamp: datetime | None = None
    episode_path: str = ""

    environment: Environment = Field(default_factory=Environment)
    warnings: list[Warning] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = Field(default_factory=list)
    styles: list[Style] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    verdicts: list[StyleVerdict] = Field(default_factory=list)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
