"""Renderability engine (Feature 013).

Decides, for every subtitle font requirement, whether the fonts attached to an
MKV container can render it, and assembles the full
:class:`~src.models.renderability.RenderabilityReport`.

The engine is **pure** (Constitution Principle I): it consumes domain models
and returns a domain model.  Reading font files and parsing subtitles happen
elsewhere (``FontFaceReaderPort`` and ``subtitle_requirements``); the only
impurities, the clock and the captured environment, are injected.

Scope
-----
Renderability is judged against the **container's attachments only**.  A font
that happens to be installed on a viewer's machine is out of scope; a later
wave can feed system faces in as additional attachments.

Behavioural rules (from the ``src.models.renderability`` contract)
-------------------------------------------------------
R5  Attachment presence is never evidence of resolution; only a name match plus
    cmap coverage is.
R6  Filenames are never identity.  Only name records decide a match.
R7  Facts and dispositions are separate.  Every ``disposition`` stays ``None``.
R8  Every timestamp is UTC.
E10 A style missing from the style block is resolved the way the renderer
    resolves it (the ``Default`` style, else the built-in Arial) and flagged.
E13 A cmap proves a glyph exists, not that it is shaped correctly, so complex
    scripts are flagged ``shaping_unverified`` and the verdict is not altered.
E14 Synthesised weight or slant is flagged ``synthesised_default``.

Verdict resolution (precedence, first match wins)
-------------------------------------------------
``UNVERIFIABLE``
    The requirement is malformed, or no verified face matches the font name
    while unreadable faces exist that could be the requested font, or an
    unreadable face with a matching name could change an imperfect outcome.
    Absence can only be asserted when nothing hides it.
``NOT_RENDERABLE``
    No face matches the font name, or a required *critical* codepoint (see
    :func:`~src.core.codepoint_ranges.is_critical`) is covered by no face of
    the matched family.
``AMBIGUOUS``
    Several faces tie for best match and would yield different verdicts.
``RENDERABLE_VIA_FALLBACK``
    The best face lacks required glyphs that other faces of the same family (or
    the viewer's system fonts, for decorative characters) must supply, or the
    only available face is a heavier or slanted substitute for the requested
    variant.
``RENDERABLE_SYNTHESISED``
    The best face covers every required codepoint but the renderer must
    synthesise weight or slant.
``RENDERABLE_AS_INTENDED``
    The best face matches name, weight and slant and covers every codepoint.

How faces are matched (grounded in libass)
------------------------------------------
Verified against libass master ``f61db567`` (latest release tag ``0.17.5``),
files ``ass_fontselect.c`` and ``ass_font.c``:

* A request is ``family`` plus a requested weight (400, or 700 for bold) and a
  slant.  The family is compared with ASCII-only case folding and a leading
  ``@`` (vertical writing) removed.
* A face matches by **family** (name IDs 1 and 16 here) and is then ranked by
  :func:`style_distance`, a port of ``font_attributes_similarity``; or by
  **face name** (name IDs 4 and 6), which ranks 0 ("chosen instantly").
* Among matching faces the lowest score wins.  For a glyph the best face
  lacks, libass searches the **same name-matching faces** for one that has it;
  faces of other families are never consulted for fallback.  Glyphs found in no
  matching face are left to the viewer's system fonts, which the engine cannot
  see.
* Synthesis: libass emboldens when ``requested_weight > face_weight + 150`` and
  italicises when italic is requested but the face is not italic.  The engine
  uses the same conditions.

The set of admissible name IDs is read from
``src.models.renderability.ADMISSIBLE_NAME_IDS`` at call time, so the
W0-C-frozen value takes effect without touching this module.

Known simplifications (all conservative or documented in a warning):
the face "bold" style flag (fsSelection bit 5) and outline flavour are not
carried by ``AttachmentFace``, libass only honours Windows-platform name
records for IDs 1 and 4, and faces without an OS/2 table are assumed to have
regular weight.
"""

from __future__ import annotations

import string
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from src.core import codepoint_ranges as cr
from src.core.style_resolution import (
    BUILTIN_DEFAULT_FONT,
    DEFAULT_STYLE_NAME,
    lookup_style,
)
from src.models import renderability as models
from src.models.renderability import (
    Attachment,
    AttachmentFace,
    Environment,
    ProvenanceEntry,
    RenderabilityReport,
    Requirement,
    Style,
    StyleVerdict,
    SubtitleTrack,
    Summary,
    Verdict,
)
from src.models.renderability import Warning as ReportWarning

REGULAR_WEIGHT: Final[int] = 400
BOLD_WEIGHT: Final[int] = 700
SYNTHESIS_WEIGHT_DELTA: Final[int] = 150
"""libass emboldens when the requested weight exceeds the face weight by more."""

RENDERABLE_VERDICTS: Final[frozenset[Verdict]] = frozenset(
    {
        Verdict.RENDERABLE_AS_INTENDED,
        Verdict.RENDERABLE_SYNTHESISED,
        Verdict.RENDERABLE_VIA_FALLBACK,
    }
)

# Rule identifiers recorded in provenance, one per decision path.
RULE_INVALID_REQUIREMENT: Final[str] = "invalid_requirement"
RULE_UNIDENTIFIED: Final[str] = "requirement_unidentified"
RULE_NO_MATCHING_FACE: Final[str] = "no_matching_face"
RULE_UNREADABLE_FACES: Final[str] = "unreadable_faces"
RULE_UNREADABLE_CANDIDATE: Final[str] = "unreadable_candidate"
RULE_CRITICAL_UNCOVERED: Final[str] = "critical_glyphs_uncovered"
RULE_TIE_DIVERGES: Final[str] = "tied_candidates_diverge"
RULE_FALLBACK_GLYPHS: Final[str] = "fallback_glyphs"
RULE_VARIANT_SUBSTITUTED: Final[str] = "variant_substituted"
RULE_SYNTHESISED: Final[str] = "synthesised"
RULE_EXACT: Final[str] = "exact"

_FACE_NAME_IDS: Final[frozenset[int]] = frozenset({4, 6})
"""Full-name and PostScript-name IDs identify one face; every other admissible
ID names a family."""
_ASCII_FOLD: Final = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)
_LEGACY_OS2_WEIGHTS: Final[dict[int, int]] = {
    1: 100,
    2: 200,
    3: 300,
    4: 350,
    5: 400,
    6: 600,
    7: 700,
    8: 800,
    9: 900,
}
"""``ass_face_get_weight``: legacy OS/2 weight classes 1-9 map to CSS weights."""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def fold_font_name(name: str) -> str:
    """Normalise a *requested* font name the way libass compares names."""
    folded = name.strip()
    if folded.startswith("@"):
        folded = folded[1:].strip()
    return folded.translate(_ASCII_FOLD)


def _fold_record(value: str) -> str:
    return value.strip().translate(_ASCII_FOLD)


def face_weight(face: AttachmentFace) -> int:
    """Return the weight libass would assign *face* (regular when undeclared)."""
    declared = face.weight
    if not declared:
        return REGULAR_WEIGHT
    return _LEGACY_OS2_WEIGHTS.get(declared, declared)


def face_is_italic(face: AttachmentFace) -> bool:
    """Return whether libass flags *face* italic.

    libass reads only fsSelection bit 0, so an oblique-only face (bit 9
    without bit 0) is *not* italic to it.
    """
    return face.slant == "italic"


def style_distance(
    face_weight_: int, face_italic: bool, request_weight: int, request_italic: bool
) -> int:
    """Port of libass ``font_attributes_similarity``; lower is a better match."""
    score = 0
    if request_italic and not face_italic:
        score += 1
    elif face_italic and not request_italic:
        score += 4
    effective = face_weight_
    if request_weight > face_weight_ + SYNTHESIS_WEIGHT_DELTA:
        effective += 120  # faux-bold offset
    return score + (73 * abs(effective - request_weight)) // 256


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Internal value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class _FaceRef:
    """A readable face prepared for matching."""

    position: int
    attachment_id: int
    face_index: int
    family_names: frozenset[str]
    face_names: frozenset[str]
    weight: int
    italic: bool
    cmap: list[cr.Range]

    @property
    def label(self) -> str:
        return f"attachment {self.attachment_id} face {self.face_index}"


@dataclass(frozen=True, eq=False)
class _UnreadableRef:
    """A face whose facts could not be read."""

    attachment_id: int
    face_index: int
    reason: str
    names: frozenset[str]

    @property
    def label(self) -> str:
        return f"attachment {self.attachment_id} face {self.face_index}"


@dataclass(frozen=True, eq=False)
class _Candidate:
    ref: _FaceRef
    by_family: bool
    score: int


@dataclass(frozen=True)
class _Request:
    """The font the renderer will ask for."""

    font_name: str
    bold: bool
    italic: bool

    @property
    def folded(self) -> str:
        return fold_font_name(self.font_name)

    @property
    def weight(self) -> int:
        return BOLD_WEIGHT if self.bold else REGULAR_WEIGHT


@dataclass(frozen=True)
class _Resolution:
    request: _Request
    missing_style: bool
    note: str


@dataclass(frozen=True, eq=False)
class _Outcome:
    verdict: Verdict
    rule: str
    reason: str
    primary: _FaceRef | None = None
    synthesised: bool = False


class _Diagnostics:
    """Ordered, de-duplicated warnings."""

    def __init__(self, initial: Iterable[ReportWarning]) -> None:
        self._items: list[ReportWarning] = []
        self._seen: set[tuple[str, str, str]] = set()
        for warning in initial:
            self.add(warning.code, warning.message, warning.detail)

    def add(self, code: str, message: str, detail: str = "") -> None:
        key = (code, message, detail)
        if key in self._seen:
            return
        self._seen.add(key)
        self._items.append(ReportWarning(code=code, message=message, detail=detail))

    @property
    def items(self) -> list[ReportWarning]:
        return list(self._items)


class _FaceIndex:
    """Readable and unreadable faces, in attachment order."""

    def __init__(self) -> None:
        self.readable: list[_FaceRef] = []
        self.unreadable: list[_UnreadableRef] = []


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RenderabilityEngine:
    """Evaluate style-requirement pairs against container font attachments.

    Parameters
    ----------
    clock:
        Returns the current time.  Injected so tests are deterministic; the
        result must be timezone-aware and is normalised to UTC (R8).
    environment:
        Runtime facts recorded in the report.  The engine never captures them
        itself, keeping it free of global lookups.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        environment: Environment | None = None,
    ) -> None:
        self._clock = clock if clock is not None else _utc_now
        self._environment = environment if environment is not None else Environment()

    # -- public API ------------------------------------------------------

    def evaluate(
        self,
        *,
        episode_path: str = "",
        attachments: Sequence[Attachment] = (),
        subtitle_tracks: Sequence[SubtitleTrack] = (),
        styles: Sequence[Style] = (),
        requirements: Sequence[Requirement] = (),
        warnings: Sequence[ReportWarning] = (),
        provenance: Sequence[ProvenanceEntry] = (),
    ) -> RenderabilityReport:
        """Evaluate every requirement and build the report.

        ``verdicts[i]`` is the verdict for ``requirements[i]``.  Upstream
        *warnings* and *provenance* (for example from subtitle extraction) are
        preserved ahead of the engine's own entries.
        """
        admissible = models.ADMISSIBLE_NAME_IDS
        family_ids = admissible - _FACE_NAME_IDS
        face_ids = admissible & _FACE_NAME_IDS

        diagnostics = _Diagnostics(warnings)
        trail: list[ProvenanceEntry] = list(provenance)

        def record(action: str, detail: str) -> None:
            trail.append(
                ProvenanceEntry(action=action, timestamp=self.now(), detail=detail)
            )

        index = self._build_index(attachments, family_ids, face_ids, diagnostics)
        styles_by_track: dict[int, list[Style]] = {}
        for style in styles:
            styles_by_track.setdefault(style.track_id, []).append(style)

        record(
            "analysis_started",
            f"attachments={len(attachments)} readable_faces={len(index.readable)} "
            f"unreadable_faces={len(index.unreadable)} styles={len(styles)} "
            f"requirements={len(requirements)} "
            f"admissible_name_ids={sorted(admissible)}",
        )
        if not index.readable and not index.unreadable:
            diagnostics.add(
                "no_attachments",
                "The container carries no readable font faces.",
                "Only the container's own attachments are considered.",
            )

        enriched: list[Requirement] = []
        verdicts: list[StyleVerdict] = []
        for requirement in requirements:
            outcome, updated = self._evaluate_requirement(
                requirement, index, styles_by_track, diagnostics
            )
            enriched.append(updated)
            verdicts.append(
                StyleVerdict(
                    style_name=requirement.style_name,
                    track_id=requirement.track_id,
                    verdict=outcome.verdict,
                    matched_face_index=(
                        outcome.primary.face_index if outcome.primary else None
                    ),
                    matched_attachment_id=(
                        outcome.primary.attachment_id if outcome.primary else None
                    ),
                    disposition=None,
                    reason=outcome.reason,
                )
            )
            record(
                "requirement_evaluated",
                f"track={requirement.track_id} style={requirement.style_name!r} "
                f"font={requirement.font_name!r} -> {outcome.verdict.value} "
                f"rule={outcome.rule}",
            )

        summary = self._summarise(styles, requirements, verdicts)
        record(
            "analysis_completed",
            f"renderable={summary.renderable} not_renderable={summary.not_renderable} "
            f"unverifiable={summary.unverifiable} ambiguous={summary.ambiguous}",
        )
        return RenderabilityReport(
            report_timestamp=self.now(),
            episode_path=episode_path,
            environment=self._environment,
            warnings=diagnostics.items,
            attachments=list(attachments),
            subtitle_tracks=list(subtitle_tracks),
            styles=list(styles),
            requirements=enriched,
            verdicts=verdicts,
            provenance=trail,
            summary=summary,
        )

    # -- clock -----------------------------------------------------------

    def now(self) -> datetime:
        """Return the injected clock's time as an aware UTC datetime (R8)."""
        stamp = self._clock()
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime (R8: UTC)")
        return stamp.astimezone(UTC)

    # -- indexing --------------------------------------------------------

    def _build_index(
        self,
        attachments: Sequence[Attachment],
        family_ids: frozenset[int],
        face_ids: frozenset[int],
        diagnostics: _Diagnostics,
    ) -> _FaceIndex:
        index = _FaceIndex()
        seen_ids: set[int] = set()
        for position, attachment in enumerate(attachments):
            if attachment.attachment_id in seen_ids:
                diagnostics.add(
                    "duplicate_attachment_id",
                    f"Attachment id {attachment.attachment_id} appears more than once.",
                    "Faces are ordered by position in the attachment list.",
                )
            seen_ids.add(attachment.attachment_id)
            if not attachment.faces:
                diagnostics.add(
                    "attachment_without_faces",
                    f"Attachment {attachment.attachment_id} produced no faces.",
                    f"mime_type={attachment.mime_type!r}",
                )
            for face in attachment.faces:
                self._index_face(
                    index, position, attachment, face, family_ids, face_ids, diagnostics
                )
        return index

    def _index_face(
        self,
        index: _FaceIndex,
        position: int,
        attachment: Attachment,
        face: AttachmentFace,
        family_ids: frozenset[int],
        face_ids: frozenset[int],
        diagnostics: _Diagnostics,
    ) -> None:
        family_names = frozenset(
            _fold_record(r.value)
            for r in face.name_records
            if r.name_id in family_ids and r.value.strip()
        )
        face_names = frozenset(
            _fold_record(r.value)
            for r in face.name_records
            if r.name_id in face_ids and r.value.strip()
        )
        reason = face.unverifiable_reason
        cmap: list[cr.Range] = []
        if reason is None:
            try:
                cmap = cr.from_models(face.cmap_ranges)
            except ValueError as exc:
                reason = f"malformed cmap ranges: {exc}"
        if reason is not None:
            index.unreadable.append(
                _UnreadableRef(
                    attachment_id=attachment.attachment_id,
                    face_index=face.face_index,
                    reason=reason,
                    names=family_names | face_names,
                )
            )
            diagnostics.add(
                "face_unverifiable",
                f"Attachment {attachment.attachment_id} face {face.face_index} "
                "could not be verified.",
                reason,
            )
            return
        if not family_names and not face_names:
            diagnostics.add(
                "face_unnamed",
                f"Attachment {attachment.attachment_id} face {face.face_index} has "
                "no admissible name record and can never be matched.",
                f"admissible name IDs: {sorted(models.ADMISSIBLE_NAME_IDS)}",
            )
        if face.weight is None:
            diagnostics.add(
                "face_weight_unknown",
                f"Attachment {attachment.attachment_id} face {face.face_index} "
                "declares no weight (no OS/2 table); regular weight is assumed.",
            )
        index.readable.append(
            _FaceRef(
                position=position,
                attachment_id=attachment.attachment_id,
                face_index=face.face_index,
                family_names=family_names,
                face_names=face_names,
                weight=face_weight(face),
                italic=face_is_italic(face),
                cmap=cmap,
            )
        )

    # -- per-requirement evaluation ---------------------------------------

    def _evaluate_requirement(
        self,
        requirement: Requirement,
        index: _FaceIndex,
        styles_by_track: dict[int, list[Style]],
        diagnostics: _Diagnostics,
    ) -> tuple[_Outcome, Requirement]:
        where = f"track {requirement.track_id} style {requirement.style_name!r}"

        try:
            declared = cr.from_models(requirement.codepoint_ranges)
        except ValueError as exc:
            diagnostics.add(
                "invalid_codepoint_range",
                f"Requirement for {where} has an invalid codepoint range.",
                str(exc),
            )
            return (
                _Outcome(
                    Verdict.UNVERIFIABLE,
                    RULE_INVALID_REQUIREMENT,
                    f"requirement data is malformed: {exc}",
                ),
                requirement,
            )

        resolution = self._resolve_request(requirement, styles_by_track)
        if resolution is None:
            diagnostics.add(
                "requirement_unidentified",
                f"Requirement for {where} names no font and no resolvable style.",
            )
            return (
                _Outcome(
                    Verdict.UNVERIFIABLE,
                    RULE_UNIDENTIFIED,
                    "the requirement names neither a font nor a style that could "
                    "supply one",
                ),
                requirement,
            )

        required = cr.strip_ignorable(declared)
        if not required:
            diagnostics.add(
                "no_required_codepoints",
                f"Requirement for {where} needs no glyphs.",
                "Only the font's presence and variant were evaluated.",
            )

        outcome = self._resolve_outcome(
            resolution.request, required, index, diagnostics, where
        )

        pua_only = cr.is_pua_only(required)
        if requirement.is_pua_only and not pua_only:
            diagnostics.add(
                "requirement_flag_corrected",
                f"Requirement for {where} claimed is_pua_only but its codepoints "
                "are not entirely private-use.",
            )
        shaping = requirement.shaping_unverified or cr.requires_complex_shaping(
            required
        )
        updated = requirement.model_copy(
            update={
                "is_pua_only": pua_only,
                "shaping_unverified": shaping,
                "missing_style_default": (
                    requirement.missing_style_default or resolution.missing_style
                ),
                "synthesised_default": (
                    requirement.synthesised_default or outcome.synthesised
                ),
            }
        )

        if resolution.missing_style:
            diagnostics.add(
                "missing_style_default",
                f"Style {requirement.style_name!r} on track {requirement.track_id} "
                "is not declared.",
                resolution.note,
            )
        if outcome.verdict in RENDERABLE_VERDICTS:
            if shaping:
                diagnostics.add(
                    "shaping_unverified",
                    f"Requirement for {where} uses a script that needs OpenType "
                    "shaping.",
                    "cmap coverage is not proof of correct shaping.",
                )
            if cr.pua_part(required):
                diagnostics.add(
                    "pua_glyph_identity_unverified",
                    f"Requirement for {where} uses private-use codepoints.",
                    "The cmap proves a glyph exists, not that it is the intended one.",
                )
        return outcome, updated

    def _resolve_request(
        self, requirement: Requirement, styles_by_track: dict[int, list[Style]]
    ) -> _Resolution | None:
        """Work out the font the renderer asks for (E10)."""
        explicit_font = requirement.font_name.strip()
        style_name = requirement.style_name.strip()
        track_styles = styles_by_track.get(requirement.track_id, [])

        base: Style | None = None
        missing = False
        note = ""
        if style_name:
            base = lookup_style(track_styles, style_name)
            if base is None and track_styles:
                missing = True
                base = lookup_style(track_styles, DEFAULT_STYLE_NAME)
                if base is not None:
                    note = (
                        f"{style_name!r} is not declared; the renderer falls back "
                        f"to style {DEFAULT_STYLE_NAME!r}."
                    )
                else:
                    note = (
                        f"{style_name!r} is not declared and there is no "
                        f"{DEFAULT_STYLE_NAME!r} style; the renderer falls back to "
                        f"its built-in default font ({BUILTIN_DEFAULT_FONT})."
                    )

        if explicit_font:
            return _Resolution(
                _Request(explicit_font, requirement.bold, requirement.italic),
                missing,
                note,
            )
        if base is not None:
            return _Resolution(
                _Request(
                    base.font_name,
                    requirement.bold or base.bold,
                    requirement.italic or base.italic,
                ),
                missing,
                note,
            )
        if missing:
            return _Resolution(
                _Request(BUILTIN_DEFAULT_FONT, requirement.bold, requirement.italic),
                missing,
                note,
            )
        return None

    # -- verdict resolution ------------------------------------------------

    def _resolve_outcome(
        self,
        request: _Request,
        required: list[cr.Range],
        index: _FaceIndex,
        diagnostics: _Diagnostics,
        where: str,
    ) -> _Outcome:
        name = request.folded
        candidates = self._candidates(request, index)
        unreadable_matches = [u for u in index.unreadable if name in u.names]

        if not candidates:
            if unreadable_matches:
                return _Outcome(
                    Verdict.UNVERIFIABLE,
                    RULE_UNREADABLE_CANDIDATE,
                    f"{len(unreadable_matches)} unreadable face(s) "
                    f"({_labels(unreadable_matches)}) carry the name "
                    f"{request.font_name!r}; their coverage cannot be verified",
                )
            if index.unreadable:
                return _Outcome(
                    Verdict.UNVERIFIABLE,
                    RULE_UNREADABLE_FACES,
                    f"no verified face matches {request.font_name!r}, but "
                    f"{len(index.unreadable)} unreadable face(s) "
                    f"({_labels(index.unreadable)}) could be the requested font",
                )
            return _Outcome(
                Verdict.NOT_RENDERABLE,
                RULE_NO_MATCHING_FACE,
                f"no attached face carries {request.font_name!r} in an admissible "
                f"name record (name IDs {sorted(models.ADMISSIBLE_NAME_IDS)})",
            )

        best = candidates[0].score
        tied = [c for c in candidates if c.score == best]
        outcome: _Outcome
        if len(tied) > 1:
            outcomes = [self._assess(c, candidates, required, request) for c in tied]
            if len({o.verdict for o in outcomes}) > 1:
                detail = "; ".join(
                    f"{c.ref.label} -> {o.verdict.value}"
                    for c, o in zip(tied, outcomes, strict=True)
                )
                outcome = _Outcome(
                    Verdict.AMBIGUOUS,
                    RULE_TIE_DIVERGES,
                    f"{len(tied)} faces match {request.font_name!r} equally well "
                    f"(score {best}) but yield different results: {detail}",
                )
            else:
                outcome = outcomes[0]
                diagnostics.add(
                    "tied_candidates",
                    f"{len(tied)} faces match {request.font_name!r} equally well for "
                    f"{where}; they agree on the verdict, so the first in attachment "
                    "order is reported.",
                    ", ".join(c.ref.label for c in tied),
                )
        else:
            outcome = self._assess(tied[0], candidates, required, request)

        if unreadable_matches and outcome.verdict is not Verdict.RENDERABLE_AS_INTENDED:
            return _Outcome(
                Verdict.UNVERIFIABLE,
                RULE_UNREADABLE_CANDIDATE,
                f"{len(unreadable_matches)} unreadable face(s) "
                f"({_labels(unreadable_matches)}) carry the requested name and "
                f"could change the outcome ({outcome.verdict.value}: "
                f"{outcome.reason})",
                primary=outcome.primary,
            )
        return outcome

    def _candidates(self, request: _Request, index: _FaceIndex) -> list[_Candidate]:
        """Faces matching the request, best first (ties keep attachment order)."""
        name = request.folded
        found: list[_Candidate] = []
        for ref in index.readable:
            if name in ref.family_names:
                score = style_distance(
                    ref.weight, ref.italic, request.weight, request.italic
                )
                found.append(_Candidate(ref, by_family=True, score=score))
            elif name in ref.face_names:
                found.append(_Candidate(ref, by_family=False, score=0))
        found.sort(key=lambda c: (c.score, c.ref.position, c.ref.face_index))
        return found

    def _assess(
        self,
        primary: _Candidate,
        pool: Sequence[_Candidate],
        required: list[cr.Range],
        request: _Request,
    ) -> _Outcome:
        """Judge *primary* as the face the renderer picks from *pool*."""
        ref = primary.ref
        missing = cr.subtract(required, ref.cmap)
        sibling_cover: list[cr.Range] = []
        for other in pool:
            if other.ref is not ref:
                sibling_cover = cr.union(sibling_cover, other.ref.cmap)
        via_family = cr.intersect(missing, sibling_cover)
        uncovered = cr.subtract(missing, sibling_cover)
        critical, decorative = cr.split_critical(uncovered)

        synth_bold = request.weight > ref.weight + SYNTHESIS_WEIGHT_DELTA
        synth_italic = request.italic and not ref.italic
        synthesised = synth_bold or synth_italic
        heavier = primary.by_family and ref.weight > request.weight + (
            SYNTHESIS_WEIGHT_DELTA
        )
        slanted = primary.by_family and ref.italic and not request.italic

        how = "family" if primary.by_family else "face"
        shape = (
            f"weight {ref.weight}, {'italic' if ref.italic else 'upright'} "
            f"(requested weight {request.weight}, "
            f"{'italic' if request.italic else 'upright'})"
        )
        synth_note = _synthesis_note(synth_bold, synth_italic)

        if critical:
            return _Outcome(
                Verdict.NOT_RENDERABLE,
                RULE_CRITICAL_UNCOVERED,
                f"{ref.label} matches {request.font_name!r} by {how} name but "
                f"{cr.count(critical)} required text codepoint(s) are covered by "
                f"no face of the family: {cr.format_codepoints(critical)}",
                primary=ref,
                synthesised=synthesised,
            )

        clauses: list[str] = []
        if via_family:
            clauses.append(
                f"{cr.count(via_family)} codepoint(s) "
                f"({cr.format_codepoints(via_family)}) come from other faces of the "
                "family"
            )
        if decorative:
            clauses.append(
                f"{cr.count(decorative)} decorative codepoint(s) "
                f"({cr.format_codepoints(decorative)}) are in no face of the "
                "family and depend on the viewer's system fonts"
            )
        if heavier or slanted:
            clauses.append(
                "the closest face is a "
                f"{'heavier' if heavier else 'slanted'} substitute for the requested "
                f"variant ({shape})"
            )
        if clauses:
            tail = f"; {synth_note}" if synth_note else ""
            rule = (
                RULE_FALLBACK_GLYPHS
                if (via_family or decorative)
                else (RULE_VARIANT_SUBSTITUTED)
            )
            return _Outcome(
                Verdict.RENDERABLE_VIA_FALLBACK,
                rule,
                f"{ref.label} matches {request.font_name!r} by {how} name; "
                + "; ".join(clauses)
                + tail,
                primary=ref,
                synthesised=synthesised,
            )
        if synthesised:
            return _Outcome(
                Verdict.RENDERABLE_SYNTHESISED,
                RULE_SYNTHESISED,
                f"{ref.label} matches {request.font_name!r} by {how} name and "
                f"covers all {cr.count(required)} required codepoint(s), but "
                f"{synth_note} ({shape})",
                primary=ref,
                synthesised=True,
            )
        return _Outcome(
            Verdict.RENDERABLE_AS_INTENDED,
            RULE_EXACT,
            f"{ref.label} matches {request.font_name!r} by {how} name, satisfies "
            f"weight and slant ({shape}) and covers all {cr.count(required)} "
            "required codepoint(s)",
            primary=ref,
        )

    # -- summary -----------------------------------------------------------

    @staticmethod
    def _summarise(
        styles: Sequence[Style],
        requirements: Sequence[Requirement],
        verdicts: Sequence[StyleVerdict],
    ) -> Summary:
        kinds = [v.verdict for v in verdicts]
        return Summary(
            total_styles=len(styles),
            total_requirements=len(requirements),
            renderable=sum(1 for k in kinds if k in RENDERABLE_VERDICTS),
            not_renderable=kinds.count(Verdict.NOT_RENDERABLE),
            unverifiable=kinds.count(Verdict.UNVERIFIABLE),
            ambiguous=kinds.count(Verdict.AMBIGUOUS),
        )


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _labels(refs: Sequence[_UnreadableRef]) -> str:
    return ", ".join(r.label for r in refs)


def _synthesis_note(synth_bold: bool, synth_italic: bool) -> str:
    if synth_bold and synth_italic:
        return "the renderer must synthesise bold and italic"
    if synth_bold:
        return "the renderer must synthesise bold"
    if synth_italic:
        return "the renderer must synthesise italic"
    return ""
