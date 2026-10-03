"""Unit tests for ASS subtitle requirement extraction (pure, no I/O)."""

from __future__ import annotations

import pytest

from src.core.renderability_engine import RenderabilityEngine
from src.core.subtitle_requirements import (
    BOLD_WEIGHT_THRESHOLD,
    SubtitleRequirements,
    extract_subtitle_requirements,
)
from src.models.renderability import (
    Attachment,
    AttachmentFace,
    CodepointRange,
    FaceNameRecord,
    Requirement,
    Verdict,
)

STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)
EVENT_FORMAT = (
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
)


def style_line(name: str, font: str, bold: int = 0, italic: int = 0) -> str:
    return (
        f"Style: {name},{font},48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"{bold},{italic},0,0,100,100,0,0,1,2,0,2,10,10,10,1"
    )


def dialogue(style: str, text: str, *, comment: bool = False) -> str:
    kind = "Comment" if comment else "Dialogue"
    return f"{kind}: 0,0:00:01.00,0:00:02.00,{style},,0,0,0,,{text}"


def script(styles: list[str], events: list[str]) -> str:
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "",
            "[V4+ Styles]",
            STYLE_FORMAT,
            *styles,
            "",
            "[Events]",
            EVENT_FORMAT,
            *events,
            "",
        ]
    )


def one(result: SubtitleRequirements) -> Requirement:
    assert len(result.requirements) == 1, result.requirements
    return result.requirements[0]


def points(requirement: Requirement) -> set[int]:
    covered: set[int] = set()
    for r in requirement.codepoint_ranges:
        covered.update(range(r.start, r.end + 1))
    return covered


def codes(result: SubtitleRequirements) -> list[str]:
    return [w.code for w in result.warnings]


def text_points(text: str) -> set[int]:
    return {ord(c) for c in text}


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------


class TestStyles:
    def test_reads_name_font_bold_italic(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [
                    style_line("Default", "Arial"),
                    style_line("Sign", "Impact", bold=-1, italic=-1),
                ],
                [],
            ),
            track_id=3,
        )
        assert [
            (s.name, s.font_name, s.bold, s.italic, s.track_id) for s in result.styles
        ] == [
            ("Default", "Arial", False, False, 3),
            ("Sign", "Impact", True, True, 3),
        ]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("-1", True), ("1", True), ("0", False), ("700", True), ("x", False)],
    )
    def test_bold_values_are_truthy_like_libass(self, raw: str, expected: bool) -> None:
        line = style_line("S", "Arial").replace(",0,0,0,0,100", f",{raw},0,0,0,100", 1)
        result = extract_subtitle_requirements(script([line], []))
        assert result.styles[0].bold is expected

    def test_ssa_v4_section_is_accepted(self) -> None:
        content = "\n".join(
            [
                "[V4 Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "TertiaryColour, BackColour, Bold, Italic",
                "Style: Default,Tahoma,20,0,0,0,0,-1,0",
                "[Events]",
                "Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                "Dialogue: Marked=0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi",
            ]
        )
        result = extract_subtitle_requirements(content)
        assert result.styles[0].font_name == "Tahoma"
        assert result.styles[0].bold is True
        assert one(result).font_name == "Tahoma"

    def test_duplicate_style_names_are_all_listed_and_the_last_wins(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("S", "First"), style_line("S", "Second")],
                [dialogue("S", "x")],
            )
        )
        assert [s.font_name for s in result.styles] == ["First", "Second"]
        assert one(result).font_name == "Second"

    def test_vertical_font_prefix_is_removed_from_requirements(self) -> None:
        result = extract_subtitle_requirements(
            script([style_line("Default", "@MS Gothic")], [dialogue("Default", "あ")])
        )
        assert result.styles[0].font_name == "@MS Gothic"  # as declared
        assert one(result).font_name == "MS Gothic"

    def test_whitespace_around_fields_is_trimmed(self) -> None:
        line = style_line("  Default ", "  Arial  ")
        result = extract_subtitle_requirements(
            script([line], [dialogue("Default", "x")])
        )
        assert one(result).font_name == "Arial"

    def test_malformed_style_lines_are_skipped_and_reported(self) -> None:
        result = extract_subtitle_requirements(
            script(["Style: ,", "Style:", style_line("Ok", "Arial")], [])
        )
        assert [s.name for s in result.styles] == ["Ok"]
        assert "malformed_style_line" in codes(result)

    def test_style_line_before_format_assumes_the_standard_order(self) -> None:
        content = "\n".join(
            [
                "[V4+ Styles]",
                "Style: Default,Arial,20,0,0,0,0,-1,0",
                "[Events]",
                EVENT_FORMAT,
                dialogue("Default", "x"),
            ]
        )
        result = extract_subtitle_requirements(content)
        assert result.styles[0].bold is True
        assert "style_format_missing" in codes(result)


# ---------------------------------------------------------------------------
# Dialogue parsing
# ---------------------------------------------------------------------------


class TestDialogue:
    def test_collects_codepoints_per_style(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "Arial"), style_line("Ar", "Tahoma")],
                [dialogue("Default", "Hello"), dialogue("Ar", "مرحبا")],
            )
        )
        assert [(r.style_name, r.font_name) for r in result.requirements] == [
            ("Default", "Arial"),
            ("Ar", "Tahoma"),
        ]
        assert points(result.requirements[0]) == text_points("Hello")
        assert points(result.requirements[1]) == text_points("مرحبا")
        assert result.dialogue_lines == 2

    def test_comment_lines_are_not_rendered(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "Arial")],
                [dialogue("Default", "ab"), dialogue("Default", "ZZZ", comment=True)],
            )
        )
        assert points(one(result)) == text_points("ab")
        assert result.dialogue_lines == 1

    def test_commas_inside_text_are_preserved(self) -> None:
        result = extract_subtitle_requirements(
            script([style_line("Default", "Arial")], [dialogue("Default", "a,b,c")])
        )
        assert 0x2C in points(one(result))

    def test_same_style_font_and_variant_merge(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "Arial")],
                [dialogue("Default", "abc"), dialogue("Default", "bcd")],
            )
        )
        requirement = one(result)
        assert points(requirement) == text_points("abcd")
        assert requirement.codepoint_ranges == [CodepointRange(start=0x61, end=0x64)]

    def test_empty_and_tag_only_lines_produce_no_requirement(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "Arial")],
                [
                    dialogue("Default", ""),
                    dialogue("Default", "{\\b1}"),
                    dialogue("Default", "{\\an8}"),
                ],
            )
        )
        assert result.requirements == []
        assert result.dialogue_lines == 3

    def test_unused_styles_produce_no_requirement(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "Arial"), style_line("Unused", "Nope")],
                [dialogue("Default", "x")],
            )
        )
        assert [r.style_name for r in result.requirements] == ["Default"]
        assert [s.name for s in result.styles] == ["Default", "Unused"]

    def test_bom_and_crlf_are_tolerated(self) -> None:
        text = script([style_line("Default", "Arial")], [dialogue("Default", "ok")])
        result = extract_subtitle_requirements("\ufeff" + text.replace("\n", "\r\n"))
        assert points(one(result)) == text_points("ok")

    def test_short_dialogue_lines_are_skipped_and_reported(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "Arial")],
                ["Dialogue: 0,0:00:01.00,Default,short", dialogue("Default", "ok")],
            )
        )
        assert result.skipped_lines == 1
        assert result.dialogue_lines == 1
        assert "malformed_dialogue_line" in codes(result)

    def test_dialogue_before_format_assumes_the_standard_order(self) -> None:
        content = "\n".join(
            [
                "[V4+ Styles]",
                STYLE_FORMAT,
                style_line("Default", "Arial"),
                "[Events]",
                dialogue("Default", "x"),
            ]
        )
        result = extract_subtitle_requirements(content)
        assert one(result).font_name == "Arial"
        assert "event_format_missing" in codes(result)

    def test_verbose_lists_every_codepoint(self) -> None:
        text = script([style_line("Default", "Arial")], [dialogue("Default", "ba")])
        assert one(extract_subtitle_requirements(text)).codepoints is None
        verbose = extract_subtitle_requirements(text, verbose=True)
        assert one(verbose).codepoints == [0x61, 0x62]

    def test_empty_script(self) -> None:
        result = extract_subtitle_requirements("")
        assert result.styles == []
        assert result.requirements == []
        assert {"no_styles", "no_dialogue"} <= set(codes(result))

    def test_garbage_never_raises(self) -> None:
        extract_subtitle_requirements("\x00\x01 not a script {\\fn")
        extract_subtitle_requirements("[Events]\nDialogue: ,,,,")
        extract_subtitle_requirements("[V4+ Styles]\nStyle: a")


# ---------------------------------------------------------------------------
# Override tags
# ---------------------------------------------------------------------------


def run(
    text: str, styles: list[str] | None = None, *, event_style: str = "Default"
) -> SubtitleRequirements:
    declared = styles or [
        style_line("Default", "Arial"),
        style_line("Alt", "Georgia", bold=1, italic=1),
    ]
    return extract_subtitle_requirements(
        script(declared, [dialogue(event_style, text)])
    )


def by_font(result: SubtitleRequirements) -> dict[tuple[str, bool, bool], set[int]]:
    return {(r.font_name, r.bold, r.italic): points(r) for r in result.requirements}


class TestOverrides:
    def test_font_override_splits_requirements(self) -> None:
        result = run("ab{\\fnImpact}cd{\\fn}ef")
        assert by_font(result) == {
            ("Arial", False, False): text_points("abef"),
            ("Impact", False, False): text_points("cd"),
        }
        assert {r.style_name for r in result.requirements} == {"Default"}

    @pytest.mark.parametrize("reset", ["\\fn", "\\fn0", "\\fn "])
    def test_font_reset_forms(self, reset: str) -> None:
        result = run("{\\fnImpact}a{" + reset + "}b")
        assert by_font(result)[("Arial", False, False)] == {ord("b")}

    def test_font_name_with_spaces_and_leading_space(self) -> None:
        result = run("{\\fn Arial Black}x")
        assert ("Arial Black", False, False) in by_font(result)

    def test_vertical_prefix_in_override_is_removed(self) -> None:
        assert ("MS Gothic", False, False) in by_font(run("{\\fn@MS Gothic}x"))

    def test_bold_and_italic_toggle(self) -> None:
        result = run("a{\\b1\\i1}b{\\b0\\i0}c")
        assert by_font(result) == {
            ("Arial", False, False): text_points("ac"),
            ("Arial", True, True): text_points("b"),
        }

    def test_bold_and_italic_reset_to_the_style_value(self) -> None:
        result = run("{\\b0\\i0}a{\\b\\i}b", event_style="Alt")
        assert by_font(result) == {
            ("Georgia", False, False): {ord("a")},
            ("Georgia", True, True): {ord("b")},
        }

    @pytest.mark.parametrize("bad", ["\\b2", "\\b-1", "\\b50", "\\i2", "\\i-1"])
    def test_invalid_arguments_restore_the_style_value(self, bad: str) -> None:
        result = run("{\\b1\\i1}{" + bad + "}x", event_style="Default")
        flags = {(b, i) for (_, b, i) in by_font(result)}
        # \b1\i1 turn both on; an invalid argument resets only its own tag.
        if bad.startswith("\\b"):
            assert flags == {(False, True)}
        else:
            assert flags == {(True, False)}

    @pytest.mark.parametrize(
        ("value", "bold"),
        [
            (100, False),
            (400, False),
            (500, False),
            (550, False),
            (551, True),
            (600, True),
            (700, True),
            (900, True),
        ],
    )
    def test_exact_weights_collapse_at_the_synthesis_threshold(
        self, value: int, bold: bool
    ) -> None:
        result = run("{\\b" + str(value) + "}x")
        assert {b for (_, b, _) in by_font(result)} == {bold}
        assert BOLD_WEIGHT_THRESHOLD == 550

    def test_approximated_weight_is_reported_but_standard_ones_are_not(self) -> None:
        assert "weight_override_approximated" in codes(run("{\\b500}x"))
        assert "weight_override_approximated" not in codes(run("{\\b700}x"))
        assert "weight_override_approximated" not in codes(run("{\\b400}x"))

    @pytest.mark.parametrize(
        "tag",
        [
            "\\bord2",
            "\\blur3",
            "\\be1",
            "\\iclip(0,0,1,1)",
            "\\fs30",
            "\\fscx90",
            "\\fsp2",
            "\\frz10",
            "\\fad(1,2)",
            "\\pos(1,2)",
            "\\an8",
            "\\c&HFFFFFF&",
            "\\1c&H0&",
        ],
    )
    def test_other_tags_never_change_the_font(self, tag: str) -> None:
        assert by_font(run("{" + tag + "}x")) == {("Arial", False, False): {ord("x")}}

    def test_parenthesised_tags_are_ignored(self) -> None:
        result = run("{\\t(0,100,\\b1\\i1\\fnImpact)}x")
        assert by_font(result) == {("Arial", False, False): {ord("x")}}

    def test_clip_with_inner_backslashes_is_skipped(self) -> None:
        result = run("{\\clip(m 0 0 l 5 5)\\b1}x")
        assert ("Arial", True, False) in by_font(result)

    def test_comment_text_in_a_block_is_never_rendered(self) -> None:
        result = run("{just a comment}a{note}b{x\\b1}c")
        assert by_font(result) == {
            ("Arial", False, False): text_points("ab"),
            ("Arial", True, False): {ord("c")},
        }

    def test_reset_returns_to_the_event_style(self) -> None:
        result = run("{\\fnImpact\\b1}a{\\r}b")
        assert by_font(result) == {
            ("Impact", True, False): {ord("a")},
            ("Arial", False, False): {ord("b")},
        }

    def test_reset_to_a_named_style_switches_style_and_font(self) -> None:
        result = run("a{\\rAlt}b{\\r}c")
        by_style = {r.style_name: r for r in result.requirements}
        assert points(by_style["Default"]) == text_points("ac")
        assert points(by_style["Alt"]) == {ord("b")}
        assert (
            by_style["Alt"].font_name,
            by_style["Alt"].bold,
            by_style["Alt"].italic,
        ) == ("Georgia", True, True)
        assert by_style["Alt"].missing_style_default is False

    def test_reset_style_lookup_is_exact_and_case_sensitive(self) -> None:
        result = run("a{\\ralt}b")
        assert {r.style_name for r in result.requirements} == {"Default"}
        assert "reset_style_unknown" in codes(result)

    def test_reset_to_a_style_then_font_reset_uses_that_styles_font(self) -> None:
        result = run("{\\rAlt\\fnImpact}a{\\fn}b")
        assert by_font(result) == {
            ("Impact", True, True): {ord("a")},
            ("Georgia", True, True): {ord("b")},
        }

    def test_drawing_mode_text_needs_no_font(self) -> None:
        result = run("a{\\p1}m 0 0 l 100 100 b 1 2 3 4 5 6{\\p0}b")
        assert by_font(result) == {("Arial", False, False): text_points("ab")}

    def test_drawing_scale_zero_is_text(self) -> None:
        assert by_font(run("{\\p0}ab")) == {("Arial", False, False): text_points("ab")}

    def test_text_after_an_unclosed_drawing_is_skipped(self) -> None:
        assert by_font(run("a{\\p2}m 0 0 l 1 1")) == {
            ("Arial", False, False): {ord("a")}
        }

    def test_pos_and_pbo_are_not_drawing_tags(self) -> None:
        assert by_font(run("{\\pos(1,2)\\pbo5}ab")) == {
            ("Arial", False, False): text_points("ab")
        }

    def test_font_override_inside_a_drawing_applies_after_it(self) -> None:
        result = run("{\\p1}m 0 0{\\p0\\fnImpact}z")
        assert by_font(result) == {("Impact", False, False): {ord("z")}}


# ---------------------------------------------------------------------------
# Escapes and braces
# ---------------------------------------------------------------------------


class TestEscapes:
    def test_hard_break_needs_no_glyph(self) -> None:
        assert points(one(run("a\\Nb"))) == text_points("ab")

    def test_soft_break_and_tab_render_as_space(self) -> None:
        assert points(one(run("a\\nb"))) == text_points("a b")
        assert points(one(run("a\tb"))) == text_points("a b")

    def test_hard_space_is_a_no_break_space(self) -> None:
        assert points(one(run("a\\hb"))) == text_points("a\u00a0b")

    def test_escaped_braces_are_literal_and_do_not_open_a_block(self) -> None:
        assert points(one(run("\\{\\b1\\}"))) == text_points("{\\b1}")

    def test_unclosed_brace_is_a_literal_character(self) -> None:
        assert points(one(run("a{b"))) == text_points("a{b")

    def test_lone_backslash_is_literal(self) -> None:
        assert points(one(run("a\\xb"))) == text_points("a\\xb")

    def test_arabic_text_and_bidi_marks_are_recorded_as_written(self) -> None:
        text = "\u200fمرحبا بالعالم\u200f"
        assert points(one(run(text))) == text_points(text)

    def test_astral_codepoints(self) -> None:
        assert points(one(run("😀"))) == {0x1F600}


# ---------------------------------------------------------------------------
# Missing styles (E10)
# ---------------------------------------------------------------------------


class TestMissingStyle:
    def test_falls_back_to_the_default_style_and_is_flagged(self) -> None:
        result = extract_subtitle_requirements(
            script([style_line("Default", "Tahoma", bold=1)], [dialogue("Gone", "x")])
        )
        requirement = one(result)
        assert requirement.style_name == "Gone"
        assert (requirement.font_name, requirement.bold) == ("Tahoma", True)
        assert requirement.missing_style_default is True

    def test_without_a_default_style_the_builtin_arial_is_used(self) -> None:
        result = extract_subtitle_requirements(
            script([style_line("Other", "Tahoma")], [dialogue("Gone", "x")])
        )
        requirement = one(result)
        assert (requirement.font_name, requirement.bold, requirement.italic) == (
            "Arial",
            False,
            False,
        )
        assert requirement.missing_style_default is True

    def test_undeclared_default_is_also_missing(self) -> None:
        result = extract_subtitle_requirements(
            script([style_line("Other", "Tahoma")], [dialogue("Default", "x")])
        )
        assert one(result).missing_style_default is True

    def test_no_styles_at_all(self) -> None:
        result = extract_subtitle_requirements(script([], [dialogue("Default", "x")]))
        assert one(result).font_name == "Arial"
        assert one(result).missing_style_default is True
        assert "no_styles" in codes(result)

    @pytest.mark.parametrize(
        "referenced", ["default", "DEFAULT", "*Default", "**Default", " Default "]
    )
    def test_default_matches_loosely(self, referenced: str) -> None:
        result = extract_subtitle_requirements(
            script([style_line("Default", "Tahoma")], [dialogue(referenced, "x")])
        )
        requirement = one(result)
        assert requirement.style_name == "Default"
        assert requirement.missing_style_default is False

    def test_other_names_match_exactly(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "A"), style_line("Sign", "B")],
                [dialogue("sign", "x")],
            )
        )
        requirement = one(result)
        assert requirement.missing_style_default is True
        assert requirement.font_name == "A"  # fell back to Default

    def test_empty_style_field_is_missing(self) -> None:
        result = extract_subtitle_requirements(
            script([style_line("Default", "Tahoma")], [dialogue("", "x")])
        )
        requirement = one(result)
        assert requirement.missing_style_default is True
        assert requirement.font_name == "Tahoma"

    def test_missing_and_declared_styles_do_not_merge(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "Tahoma")],
                [dialogue("Default", "a"), dialogue("Gone", "b")],
            )
        )
        assert [
            (r.style_name, r.missing_style_default) for r in result.requirements
        ] == [
            ("Default", False),
            ("Gone", True),
        ]

    def test_font_override_in_a_missing_style_keeps_the_flag(self) -> None:
        result = extract_subtitle_requirements(
            script(
                [style_line("Default", "Tahoma")], [dialogue("Gone", "{\\fnImpact}x")]
            )
        )
        requirement = one(result)
        assert (requirement.font_name, requirement.missing_style_default) == (
            "Impact",
            True,
        )


# ---------------------------------------------------------------------------
# Extractor → engine
# ---------------------------------------------------------------------------


def _face(
    family: str, cmap: tuple[tuple[int, int], ...], weight: int = 400
) -> AttachmentFace:
    return AttachmentFace(
        face_index=0,
        name_records=[
            FaceNameRecord(
                name_id=1, platform_id=3, encoding_id=1, language_id=0x409, value=family
            )
        ],
        cmap_ranges=[CodepointRange(start=a, end=b) for a, b in cmap],
        weight=weight,
    )


def _attach(attachment_id: int, face: AttachmentFace) -> Attachment:
    return Attachment(
        attachment_id=attachment_id,
        attachment_filename=f"{attachment_id}.ttf",
        mime_type="font/ttf",
        faces=[face],
    )


class TestExtractorFeedsEngine:
    LATIN = ((0x20, 0x7E),)
    ARABIC = ((0x20, 0x20), (0x0600, 0x06FF), (0x200F, 0x200F))

    def _run(
        self, content: str, attachments: list[Attachment]
    ) -> tuple[list[Verdict], list[str]]:
        extracted = extract_subtitle_requirements(content)
        report = RenderabilityEngine().evaluate(
            attachments=attachments,
            styles=extracted.styles,
            requirements=extracted.requirements,
            warnings=extracted.warnings,
        )
        return [v.verdict for v in report.verdicts], [
            v.style_name for v in report.verdicts
        ]

    def test_arabic_style_with_a_latin_only_font_is_not_renderable(self) -> None:
        content = script(
            [style_line("Default", "Arial"), style_line("Ar", "Tahoma")],
            [dialogue("Default", "Hello"), dialogue("Ar", "مرحبا")],
        )
        verdicts, names = self._run(
            content,
            [
                _attach(1, _face("Arial", self.LATIN)),
                _attach(2, _face("Tahoma", self.LATIN)),
            ],
        )
        assert dict(zip(names, verdicts, strict=True)) == {
            "Default": Verdict.RENDERABLE_AS_INTENDED,
            "Ar": Verdict.NOT_RENDERABLE,
        }

    def test_arabic_style_with_a_covering_font_is_renderable(self) -> None:
        content = script(
            [style_line("Ar", "Tahoma")], [dialogue("Ar", "\u200fمرحبا\u200f")]
        )
        verdicts, _ = self._run(content, [_attach(1, _face("Tahoma", self.ARABIC))])
        assert verdicts == [Verdict.RENDERABLE_AS_INTENDED]

    def test_bold_override_without_a_bold_face_is_synthesised(self) -> None:
        content = script(
            [style_line("Default", "Arial")], [dialogue("Default", "a{\\b1}b")]
        )
        verdicts, _ = self._run(content, [_attach(1, _face("Arial", self.LATIN))])
        assert verdicts == [
            Verdict.RENDERABLE_AS_INTENDED,
            Verdict.RENDERABLE_SYNTHESISED,
        ]

    def test_inline_font_override_to_an_unattached_font_is_not_renderable(self) -> None:
        content = script(
            [style_line("Default", "Arial")], [dialogue("Default", "a{\\fnImpact}b")]
        )
        verdicts, _ = self._run(content, [_attach(1, _face("Arial", self.LATIN))])
        assert verdicts == [Verdict.RENDERABLE_AS_INTENDED, Verdict.NOT_RENDERABLE]

    def test_missing_style_is_flagged_end_to_end(self) -> None:
        content = script([style_line("Default", "Arial")], [dialogue("Gone", "x")])
        extracted = extract_subtitle_requirements(content)
        report = RenderabilityEngine().evaluate(
            attachments=[_attach(1, _face("Arial", self.LATIN))],
            styles=extracted.styles,
            requirements=extracted.requirements,
        )
        assert report.verdicts[0].verdict is Verdict.RENDERABLE_AS_INTENDED
        assert report.requirements[0].missing_style_default is True

    def test_drawings_do_not_create_phantom_requirements(self) -> None:
        content = script(
            [style_line("Default", "Arial")],
            [dialogue("Default", "{\\p1}m 0 0 l 10 10{\\p0}")],
        )
        assert extract_subtitle_requirements(content).requirements == []
