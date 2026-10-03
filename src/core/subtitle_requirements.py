"""ASS subtitle requirement extraction (Feature 013).

Turns the text of an ASS/SSA script into the facts the renderability engine
consumes: the declared styles, and one :class:`Requirement` per distinct
(style, font, bold, italic) combination actually used by dialogue, each with
the union of the codepoints it must render.

Pure (Constitution Principle I): it takes a ``str`` and returns models.  Reading
the file or the container is the caller's job.

Semantics follow libass (verified against master ``f61db567``):

* Override blocks run from ``{`` to the first following ``}``.  A ``{`` with no
  later ``}`` is a literal character.  Text inside a block is never rendered.
* ``\\fn<name>`` sets the font (``\\fn`` and ``\\fn0`` restore the style's font),
  ``\\b`` and ``\\i`` set weight and slant (invalid arguments restore the
  style's), ``\\r`` restores the event's style and ``\\r<name>`` switches to the
  named style (exact, case-sensitive match; unknown names restore the event's
  style), ``\\p<n>`` with ``n > 0`` turns the following text into a vector
  drawing that needs no font.
* Tags nested in parentheses (``\\t(...)``, ``\\clip(...)``) never change the
  font and are skipped.
* Escapes: ``\\N`` is a line break, ``\\n`` and a tab render as a space, ``\\h``
  is a no-break space (U+00A0), ``\\{`` and ``\\}`` are literal braces.
* A dialogue style that is not declared is resolved like the renderer does (the
  ``Default`` style, else the built-in Arial) and flagged ``missing_style_default``
  (E10).

Limits: the model stores bold as a bool, so exact ``\\b<weight>`` overrides are
collapsed at libass's own synthesis threshold and reported in a warning.
``[Fonts]`` sections (fonts embedded in the script itself) are not read.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from src.core import codepoint_ranges as cr
from src.core.style_resolution import (
    BUILTIN_DEFAULT_FONT,
    DEFAULT_STYLE_NAME,
    clean_font_name,
    lookup_style,
)
from src.models.renderability import Requirement, Style
from src.models.renderability import Warning as ReportWarning

STYLE_SECTIONS: Final[frozenset[str]] = frozenset(
    {"[v4+ styles]", "[v4 styles]", "[v4++ styles]"}
)
EVENTS_SECTION: Final[str] = "[events]"

_DEFAULT_STYLE_FORMAT: Final[tuple[str, ...]] = (
    "name",
    "fontname",
    "fontsize",
    "primarycolour",
    "secondarycolour",
    "outlinecolour",
    "backcolour",
    "bold",
    "italic",
)
_DEFAULT_EVENT_FORMAT: Final[tuple[str, ...]] = (
    "layer",
    "start",
    "end",
    "style",
    "name",
    "marginl",
    "marginr",
    "marginv",
    "effect",
    "text",
)

BOLD_WEIGHT_THRESHOLD: Final[int] = 550
"""``\\b<weight>`` above this counts as bold (libass synthesises bold for a
regular face once the request exceeds 400 + 150)."""

_LEADING_INT: Final = re.compile(r"\s*([+-]?\d+)")
_BOLD_TAG: Final = re.compile(r"b(-?\d+)?\s*")
_ITALIC_TAG: Final = re.compile(r"i(-?\d+)?\s*")
_DRAWING_TAG: Final = re.compile(r"p(-?\d+)\s*")


@dataclass(frozen=True)
class SubtitleRequirements:
    """Everything the engine needs from one subtitle track."""

    styles: list[Style]
    requirements: list[Requirement]
    warnings: list[ReportWarning]
    dialogue_lines: int
    skipped_lines: int


@dataclass(frozen=True)
class _State:
    """The font the renderer would ask for at a point in a dialogue line."""

    style_name: str
    missing: bool
    style_font: str
    style_bold: bool
    style_italic: bool
    font: str
    bold: bool
    italic: bool

    @classmethod
    def for_style(
        cls, name: str, font: str, bold: bool, italic: bool, *, missing: bool
    ) -> _State:
        return cls(name, missing, font, bold, italic, font, bold, italic)


def _leading_int(text: str) -> int | None:
    match = _LEADING_INT.match(text)
    return int(match.group(1)) if match else None


def _split_tags(block: str) -> list[str]:
    """Split an override block into tags; backslashes inside ``(...)`` stay put."""
    tags: list[str] = []
    current: list[str] | None = None
    depth = 0
    for char in block:
        if char == "\\" and depth == 0:
            if current is not None:
                tags.append("".join(current))
            current = []
            continue
        if current is None:  # comment text before the first tag
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        current.append(char)
    if current is not None:
        tags.append("".join(current))
    return tags


class _Collector:
    """Accumulates requirements while walking dialogue text."""

    def __init__(self, styles: Sequence[Style], track_id: int) -> None:
        self.styles = styles
        self.track_id = track_id
        self._codepoints: dict[tuple[str, str, bool, bool], set[int]] = {}
        self._missing: dict[tuple[str, str, bool, bool], bool] = {}
        self._warnings: dict[tuple[str, str], str] = {}

    # -- warnings ----------------------------------------------------------

    def warn(self, code: str, message: str, detail: str = "") -> None:
        self._warnings.setdefault((code, message), detail)

    @property
    def warnings(self) -> list[ReportWarning]:
        return [
            ReportWarning(code=code, message=message, detail=detail)
            for (code, message), detail in self._warnings.items()
        ]

    # -- style states ------------------------------------------------------

    def state_for_event_style(self, name: str) -> _State:
        declared = lookup_style(self.styles, name)
        if declared is not None:
            return _State.for_style(
                declared.name.strip(),
                clean_font_name(declared.font_name),
                declared.bold,
                declared.italic,
                missing=False,
            )
        fallback = lookup_style(self.styles, DEFAULT_STYLE_NAME)
        referenced = name.strip().lstrip("*")
        if fallback is not None:
            return _State.for_style(
                referenced,
                clean_font_name(fallback.font_name),
                fallback.bold,
                fallback.italic,
                missing=True,
            )
        return _State.for_style(
            referenced, BUILTIN_DEFAULT_FONT, False, False, missing=True
        )

    def state_for_reset(self, name: str, event_state: _State) -> _State:
        """``\\r<name>``: exact, case-sensitive; unknown names restore the event."""
        for style in reversed(self.styles):
            if style.name.strip() == name:
                return _State.for_style(
                    style.name.strip(),
                    clean_font_name(style.font_name),
                    style.bold,
                    style.italic,
                    missing=False,
                )
        self.warn(
            "reset_style_unknown",
            f"\\r{name} names a style that is not declared; the event style is "
            "restored instead.",
        )
        return event_state

    # -- recording ---------------------------------------------------------

    def add(self, state: _State, codepoint: int) -> None:
        key = (state.style_name, state.font, state.bold, state.italic)
        self._codepoints.setdefault(key, set()).add(codepoint)
        if state.missing:
            self._missing[key] = True

    def requirements(self, *, verbose: bool) -> list[Requirement]:
        built: list[Requirement] = []
        for key, codepoints in self._codepoints.items():
            style_name, font, bold, italic = key
            built.append(
                Requirement(
                    track_id=self.track_id,
                    style_name=style_name,
                    font_name=font,
                    bold=bold,
                    italic=italic,
                    codepoint_ranges=cr.to_models(cr.from_codepoints(codepoints)),
                    codepoints=sorted(codepoints) if verbose else None,
                    missing_style_default=self._missing.get(key, False),
                )
            )
        return built

    # -- override tags -----------------------------------------------------

    def apply_block(
        self, block: str, state: _State, event_state: _State, drawing: bool
    ) -> tuple[_State, bool]:
        for tag in _split_tags(block):
            if tag.startswith("fn"):
                argument = tag[2:].strip()
                if not argument or argument == "0":
                    font = state.style_font
                else:
                    font = clean_font_name(argument)
                state = _replace(state, font=font)
            elif (match := _BOLD_TAG.fullmatch(tag)) is not None:
                state = _replace(state, bold=self._bold_value(match.group(1), state))
            elif (match := _ITALIC_TAG.fullmatch(tag)) is not None:
                value = _leading_int(match.group(1) or "")
                italic = state.style_italic if value not in (0, 1) else value == 1
                state = _replace(state, italic=italic)
            elif (match := _DRAWING_TAG.fullmatch(tag)) is not None:
                drawing = int(match.group(1)) > 0
            elif tag.startswith("r"):
                name = tag[1:].strip()
                state = self.state_for_reset(name, event_state) if name else event_state
        return state, drawing

    def _bold_value(self, argument: str | None, state: _State) -> bool:
        value = _leading_int(argument or "")
        if value is None or not (value in (0, 1) or value >= 100):
            return state.style_bold
        if value in (0, 1):
            return value == 1
        if value not in (400, 700):
            self.warn(
                "weight_override_approximated",
                f"\\b{value} was collapsed to "
                f"{'bold' if value > BOLD_WEIGHT_THRESHOLD else 'regular'}.",
                "Requirements record weight as a bool.",
            )
        return value > BOLD_WEIGHT_THRESHOLD

    # -- dialogue text -----------------------------------------------------

    def consume_text(self, text: str, event_style: str) -> None:
        event_state = self.state_for_event_style(event_style)
        state = event_state
        drawing = False
        i, n = 0, len(text)
        while i < n:
            char = text[i]
            if char == "{":
                close = text.find("}", i)
                if close != -1:
                    state, drawing = self.apply_block(
                        text[i + 1 : close], state, event_state, drawing
                    )
                    i = close + 1
                    continue
            if drawing:
                following = text.find("{", i + 1)
                i = n if following == -1 else following
                continue
            if char == "\\" and i + 1 < n:
                escaped = text[i + 1]
                if escaped == "N":
                    i += 2
                    continue
                if escaped == "n":
                    self.add(state, 0x20)
                    i += 2
                    continue
                if escaped == "h":
                    self.add(state, 0xA0)
                    i += 2
                    continue
                if escaped in "{}":
                    self.add(state, ord(escaped))
                    i += 2
                    continue
            self.add(state, 0x20 if char == "\t" else ord(char))
            i += 1


def _replace(
    state: _State,
    *,
    font: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> _State:
    return _State(
        style_name=state.style_name,
        missing=state.missing,
        style_font=state.style_font,
        style_bold=state.style_bold,
        style_italic=state.style_italic,
        font=state.font if font is None else font,
        bold=state.bold if bold is None else bold,
        italic=state.italic if italic is None else italic,
    )


# ---------------------------------------------------------------------------
# Script parsing
# ---------------------------------------------------------------------------


def _format_fields(value: str) -> list[str]:
    return [field.strip().lower() for field in value.split(",")]


def _field(values: Sequence[str], fields: Sequence[str], name: str) -> str | None:
    try:
        position = fields.index(name)
    except ValueError:
        return None
    return values[position].strip() if position < len(values) else None


def extract_subtitle_requirements(
    content: str, *, track_id: int = 0, verbose: bool = False
) -> SubtitleRequirements:
    """Extract styles and font requirements from an ASS/SSA script.

    Never raises on malformed input: bad lines are skipped and reported in
    ``warnings``.  ``verbose=True`` additionally lists every codepoint.
    """
    warnings: dict[tuple[str, str], str] = {}

    def warn(code: str, message: str, detail: str = "") -> None:
        warnings.setdefault((code, message), detail)

    styles: list[Style] = []
    events: list[tuple[str, str]] = []
    style_fields: list[str] | None = None
    event_fields: list[str] | None = None
    section = ""
    bad_styles = 0
    bad_events = 0
    dialogue_lines = 0

    for raw in content.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.lower()
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip().lower()
        value = value.lstrip()
        if section in STYLE_SECTIONS:
            if key == "format":
                style_fields = _format_fields(value)
            elif key == "style":
                if style_fields is None:
                    warn(
                        "style_format_missing",
                        "A Style line precedes any Format line; the standard "
                        "V4+ field order is assumed.",
                    )
                    style_fields = list(_DEFAULT_STYLE_FORMAT)
                values = value.split(",", len(style_fields) - 1)
                name = _field(values, style_fields, "name")
                font = _field(values, style_fields, "fontname")
                if not name or font is None:
                    bad_styles += 1
                    continue
                bold = _field(values, style_fields, "bold")
                italic = _field(values, style_fields, "italic")
                styles.append(
                    Style(
                        name=name,
                        font_name=font or BUILTIN_DEFAULT_FONT,
                        bold=bool(_leading_int(bold or "")),
                        italic=bool(_leading_int(italic or "")),
                        track_id=track_id,
                    )
                )
        elif section == EVENTS_SECTION:
            if key == "format":
                event_fields = _format_fields(value)
            elif key == "dialogue":
                if event_fields is None:
                    warn(
                        "event_format_missing",
                        "A Dialogue line precedes any Format line; the standard "
                        "ASS field order is assumed.",
                    )
                    event_fields = list(_DEFAULT_EVENT_FORMAT)
                values = value.split(",", len(event_fields) - 1)
                style_name = _field(values, event_fields, "style")
                text_position = (
                    event_fields.index("text") if "text" in event_fields else -1
                )
                if (
                    style_name is None
                    or text_position < 0
                    or text_position >= len(values)
                    or len(values) < len(event_fields)
                ):
                    bad_events += 1
                    continue
                dialogue_lines += 1
                events.append((style_name, values[text_position]))

    if bad_styles:
        warn(
            "malformed_style_line",
            f"{bad_styles} Style line(s) were skipped.",
            "A style needs a name and a font name.",
        )
    if bad_events:
        warn(
            "malformed_dialogue_line",
            f"{bad_events} Dialogue line(s) were skipped.",
            "A dialogue line needs every field declared by Format.",
        )
    if not styles:
        warn(
            "no_styles",
            "The script declares no styles.",
            "Every dialogue line uses the renderer's built-in default style.",
        )
    if not events:
        warn("no_dialogue", "The script contains no dialogue lines.")

    collector = _Collector(styles, track_id)
    for style_name, text in events:
        collector.consume_text(text, style_name)

    merged: list[ReportWarning] = [
        ReportWarning(code=code, message=message, detail=detail)
        for (code, message), detail in warnings.items()
    ]
    merged.extend(collector.warnings)
    return SubtitleRequirements(
        styles=styles,
        requirements=collector.requirements(verbose=verbose),
        warnings=merged,
        dialogue_lines=dialogue_lines,
        skipped_lines=bad_events,
    )
