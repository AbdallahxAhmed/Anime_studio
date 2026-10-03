"""Tests for the renderability service.

The service's only collaborator is ``FontFaceReaderPort``.  Most tests use the
real fontTools adapter on fonts generated in ``tmp_path`` (nothing about the
font reading is mocked); a small fake port covers threading and failure paths
the real adapter promises never to produce.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path


from src.adapters.font_face_reader import FontFaceReaderAdapter
from src.core.renderability_engine import RenderabilityEngine
from src.core.renderability_service import (
    DEFAULT_TRACK,
    RenderabilityService,
    capture_environment,
)
from src.models.renderability import (
    AttachmentFace,
    RenderabilityReport,
    SubtitleTrack,
    Verdict,
)
from src.ports.font_face_reader import FontFaceReaderPort
from tests.unit.core.font_builders import (
    ARABIC,
    LATIN,
    FaceSpec,
    build_collection,
    build_font,
    build_truncated,
    span,
)

STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)
EVENT_FORMAT = (
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
)


def _style(name: str, font: str, bold: int = 0, italic: int = 0) -> str:
    return (
        f"Style: {name},{font},48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"{bold},{italic},0,0,100,100,0,0,1,2,0,2,10,10,10,1"
    )


def _line(style: str, text: str) -> str:
    return f"Dialogue: 0,0:00:01.00,0:00:02.00,{style},,0,0,0,,{text}"


def _script(styles: list[str], lines: list[str]) -> str:
    return "\n".join(
        ["[V4+ Styles]", STYLE_FORMAT, *styles, "", "[Events]", EVENT_FORMAT, *lines]
    )


class _Clock:
    def __init__(self) -> None:
        self._now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


def _service() -> RenderabilityService:
    return RenderabilityService(
        FontFaceReaderAdapter(), engine=RenderabilityEngine(clock=_Clock())
    )


def _verdicts(report: RenderabilityReport) -> dict[str, Verdict]:
    return {f"{v.style_name}": v.verdict for v in report.verdicts}


# ---------------------------------------------------------------------------
# Real fonts, real adapter
# ---------------------------------------------------------------------------


class TestWithRealFonts:
    async def test_end_to_end_mixed_script(self, tmp_path: Path) -> None:
        regular = build_font(tmp_path, "a.ttf", FaceSpec("Foo"))
        bold = build_font(tmp_path, "b.ttf", FaceSpec("Foo", style="Bold", weight=700))
        arabic = build_font(tmp_path, "c.ttf", FaceSpec("Bar", codepoints=ARABIC))
        content = _script(
            [
                _style("Default", "Foo"),
                _style("Ar", "Bar"),
                _style("Gone2", "Missing"),
            ],
            [
                _line("Default", "Hello {\\b1}world"),
                _line("Ar", "\u200fمرحبا\u200f"),
                _line("Gone", "fallback to Default"),
                _line("Gone2", "x"),
            ],
        )
        report = await _service().analyse(
            episode_path=tmp_path / "ep01.mkv",
            subtitle_content=content,
            font_paths=[regular, bold, arabic],
        )

        by_key = {
            (v.style_name, r.bold): v.verdict
            for v, r in zip(report.verdicts, report.requirements, strict=True)
        }
        assert by_key[("Default", False)] is Verdict.RENDERABLE_AS_INTENDED
        assert by_key[("Default", True)] is Verdict.RENDERABLE_AS_INTENDED
        assert by_key[("Ar", False)] is Verdict.RENDERABLE_AS_INTENDED
        assert by_key[("Gone", False)] is Verdict.RENDERABLE_AS_INTENDED
        assert by_key[("Gone2", False)] is Verdict.NOT_RENDERABLE
        bold_verdict = next(
            v
            for v, r in zip(report.verdicts, report.requirements, strict=True)
            if r.bold
        )
        assert (
            bold_verdict.matched_attachment_id,
            bold_verdict.matched_face_index,
        ) == (
            2,
            0,
        )
        gone = next(r for r in report.requirements if r.style_name == "Gone")
        assert gone.missing_style_default is True

        assert report.episode_path == str(tmp_path / "ep01.mkv")
        assert [a.attachment_id for a in report.attachments] == [1, 2, 3]
        assert [a.attachment_filename for a in report.attachments] == [
            "a.ttf",
            "b.ttf",
            "c.ttf",
        ]
        assert all(a.mime_type == "font/ttf" for a in report.attachments)
        assert report.subtitle_tracks == [DEFAULT_TRACK]
        assert report.summary.total_requirements == len(report.requirements)
        assert report.report_timestamp is not None
        assert report.report_timestamp.utcoffset() == timedelta(0)
        assert (
            RenderabilityReport.model_validate_json(report.model_dump_json()) == report
        )

    async def test_collection_face_selection(self, tmp_path: Path) -> None:
        collection = build_collection(
            tmp_path,
            "Foo.ttc",
            [
                FaceSpec("Foo"),
                FaceSpec("Foo", style="Bold", weight=700),
                FaceSpec("Foo", style="Italic", italic=True),
                FaceSpec("Bar", codepoints=ARABIC),
            ],
        )
        content = _script(
            [_style("Default", "Foo"), _style("Ar", "Bar"), _style("B", "Foo", bold=1)],
            [_line("Default", "abc"), _line("B", "abc"), _line("Ar", "مرحبا")],
        )
        report = await _service().analyse(
            episode_path="ep.mkv", subtitle_content=content, font_paths=[collection]
        )
        attachment = report.attachments[0]
        assert attachment.mime_type == "font/collection"
        assert [f.face_index for f in attachment.faces] == [0, 1, 2, 3]
        picks = {
            v.style_name: (v.matched_face_index, v.verdict) for v in report.verdicts
        }
        assert picks["Default"] == (0, Verdict.RENDERABLE_AS_INTENDED)
        assert picks["B"] == (1, Verdict.RENDERABLE_AS_INTENDED)
        assert picks["Ar"] == (3, Verdict.RENDERABLE_AS_INTENDED)

    async def test_pua_only_font(self, tmp_path: Path) -> None:
        icons = build_font(
            tmp_path, "icons.ttf", FaceSpec("Icons", codepoints=span((0xE000, 0xE0FF)))
        )
        content = _script(
            [_style("Glyph", "Icons"), _style("Text", "Icons")],
            [_line("Glyph", "\ue001\ue002"), _line("Text", "plain")],
        )
        report = await _service().analyse(
            episode_path="ep.mkv", subtitle_content=content, font_paths=[icons]
        )
        verdicts = _verdicts(report)
        assert verdicts["Glyph"] is Verdict.RENDERABLE_AS_INTENDED
        assert verdicts["Text"] is Verdict.NOT_RENDERABLE
        glyph = next(r for r in report.requirements if r.style_name == "Glyph")
        assert glyph.is_pua_only is True

    async def test_truncated_and_empty_and_missing_files_are_unverifiable(
        self, tmp_path: Path
    ) -> None:
        good = build_font(tmp_path, "good.ttf", FaceSpec("Foo"))
        truncated = build_truncated(tmp_path, "cut.ttf", good)
        empty = tmp_path / "empty.ttf"
        empty.write_bytes(b"")
        missing = tmp_path / "does_not_exist.ttf"
        content = _script(
            [_style("Default", "Foo"), _style("Other", "Nowhere")],
            [_line("Default", "abc"), _line("Other", "abc")],
        )
        report = await _service().analyse(
            episode_path="ep.mkv",
            subtitle_content=content,
            font_paths=[good, truncated, empty, missing],
        )
        verdicts = _verdicts(report)
        assert verdicts["Default"] is Verdict.RENDERABLE_AS_INTENDED
        assert verdicts["Other"] is Verdict.UNVERIFIABLE
        unreadable = [
            a.attachment_filename
            for a in report.attachments
            if all(f.unverifiable_reason for f in a.faces)
        ]
        assert unreadable == ["cut.ttf", "empty.ttf", "does_not_exist.ttf"]
        assert [w.code for w in report.warnings].count("face_unverifiable") == 3

    async def test_filename_never_decides_identity(self, tmp_path: Path) -> None:
        imposter = build_font(tmp_path, "Arial.ttf", FaceSpec("Foo"))
        content = _script([_style("Default", "Arial")], [_line("Default", "abc")])
        report = await _service().analyse(
            episode_path="ep.mkv", subtitle_content=content, font_paths=[imposter]
        )
        assert report.verdicts[0].verdict is Verdict.NOT_RENDERABLE

    async def test_weight_comes_from_the_font_not_its_name(
        self, tmp_path: Path
    ) -> None:
        mislabelled = build_font(
            tmp_path, "FooBold.ttf", FaceSpec("Foo", style="Bold", weight=400)
        )
        content = _script([_style("Default", "Foo", bold=1)], [_line("Default", "abc")])
        report = await _service().analyse(
            episode_path="ep.mkv", subtitle_content=content, font_paths=[mislabelled]
        )
        assert report.verdicts[0].verdict is Verdict.RENDERABLE_SYNTHESISED

    async def test_provenance_records_parsing_and_every_font_file(
        self, tmp_path: Path
    ) -> None:
        a = build_font(tmp_path, "a.ttf", FaceSpec("Foo"))
        b = build_truncated(tmp_path, "b.ttf", a)
        content = _script([_style("Default", "Foo")], [_line("Default", "abc")])
        report = await _service().analyse(
            episode_path="ep.mkv", subtitle_content=content, font_paths=[a, b]
        )
        actions = [p.action for p in report.provenance]
        assert actions == [
            "subtitle_parsed",
            "font_file_read",
            "font_file_read",
            "analysis_started",
            "requirement_evaluated",
            "analysis_completed",
        ]
        details = [p.detail for p in report.provenance]
        assert "styles=1 dialogue_lines=1" in details[0]
        assert "file='a.ttf' faces=1 unreadable_faces=0" in details[1]
        assert "file='b.ttf' faces=1 unreadable_faces=1" in details[2]
        stamps = [p.timestamp for p in report.provenance]
        assert stamps == sorted(stamps)
        assert all(s.utcoffset() == timedelta(0) for s in stamps)

    async def test_custom_track_is_recorded(self, tmp_path: Path) -> None:
        font = build_font(tmp_path, "a.ttf", FaceSpec("Foo"))
        track = SubtitleTrack(track_id=4, codec="ass", language="ara", is_default=False)
        content = _script([_style("Default", "Foo")], [_line("Default", "abc")])
        report = await _service().analyse(
            episode_path="ep.mkv",
            subtitle_content=content,
            font_paths=[font],
            track=track,
        )
        assert report.subtitle_tracks == [track]
        assert {s.track_id for s in report.styles} == {4}
        assert {r.track_id for r in report.requirements} == {4}
        assert {v.track_id for v in report.verdicts} == {4}

    async def test_no_fonts_and_no_dialogue(self) -> None:
        report = await _service().analyse(
            episode_path="ep.mkv", subtitle_content="", font_paths=[]
        )
        assert report.verdicts == []
        codes = {w.code for w in report.warnings}
        assert {"no_styles", "no_dialogue", "no_attachments"} <= codes


# ---------------------------------------------------------------------------
# Fake port: threading and failure paths
# ---------------------------------------------------------------------------


class _FakeReader:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[Path] = []
        self.threads: set[int] = set()
        self._fail = fail

    def read_faces(self, font_path: Path) -> list[AttachmentFace]:
        self.calls.append(font_path)
        self.threads.add(threading.get_ident())
        if self._fail:
            raise PermissionError("denied")
        return [AttachmentFace(face_index=0, unverifiable_reason="fake")]


class TestWithFakePort:
    def test_fake_satisfies_the_port(self) -> None:
        assert isinstance(_FakeReader(), FontFaceReaderPort)

    async def test_font_files_are_read_off_the_event_loop_thread(self) -> None:
        reader = _FakeReader()
        service = RenderabilityService(reader)
        await service.analyse(
            episode_path="ep.mkv",
            subtitle_content="",
            font_paths=[Path("a.ttf")],
        )
        assert reader.threads
        assert threading.get_ident() not in reader.threads

    async def test_duplicate_paths_are_read_once_in_order(self) -> None:
        reader = _FakeReader()
        report = await RenderabilityService(reader).analyse(
            episode_path="ep.mkv",
            subtitle_content="",
            font_paths=[Path("b.ttf"), Path("a.ttf"), Path("b.ttf")],
        )
        assert reader.calls == [Path("b.ttf"), Path("a.ttf")]
        assert [a.attachment_filename for a in report.attachments] == ["b.ttf", "a.ttf"]

    async def test_an_os_error_becomes_an_unverifiable_face(self) -> None:
        report = await RenderabilityService(_FakeReader(fail=True)).analyse(
            episode_path="ep.mkv",
            subtitle_content=_script(
                [_style("Default", "Foo")], [_line("Default", "a")]
            ),
            font_paths=[Path("locked.ttf")],
        )
        face = report.attachments[0].faces[0]
        assert face.unverifiable_reason is not None
        assert "denied" in face.unverifiable_reason
        assert report.verdicts[0].verdict is Verdict.UNVERIFIABLE

    async def test_concurrent_analyses_do_not_interfere(self) -> None:
        reader = _FakeReader()
        service = RenderabilityService(reader)
        reports = await asyncio.gather(
            *(
                service.analyse(
                    episode_path=f"ep{i}.mkv",
                    subtitle_content=_script(
                        [_style("Default", "Foo")], [_line("Default", "a" * (i + 1))]
                    ),
                    font_paths=[Path(f"{i}.ttf")],
                )
                for i in range(5)
            )
        )
        assert [r.episode_path for r in reports] == [f"ep{i}.mkv" for i in range(5)]
        assert [r.attachments[0].attachment_filename for r in reports] == [
            f"{i}.ttf" for i in range(5)
        ]


# ---------------------------------------------------------------------------
# Environment capture
# ---------------------------------------------------------------------------


def test_capture_environment_reports_runtime_facts() -> None:
    environment = capture_environment()
    assert environment.fonttools_version
    assert environment.python_version.count(".") >= 1
    assert environment.platform


async def test_default_engine_records_the_captured_environment(tmp_path: Path) -> None:
    report = await RenderabilityService(FontFaceReaderAdapter()).analyse(
        episode_path="ep.mkv", subtitle_content="", font_paths=[]
    )
    assert report.environment == capture_environment()


def test_latin_fixture_is_ascii_printable() -> None:
    assert min(LATIN) == 0x20 and max(LATIN) == 0x7E
