"""Pipeline wiring for Feature 013: subtitle analysis emits a RenderabilityReport.

Real service, real fontTools adapter, real generated fonts and a real subtitle
file; only the I/O boundaries the runner owns (subprocess, filesystem, font
resolver, scanner) are mocked, exactly as in ``test_pipeline_runner``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.dependency_checker import ToolRegistry
from src.adapters.font_face_reader import FontFaceReaderAdapter
from src.config import AppConfig
from src.core.font_ingestion import FontIngestionService
from src.core.font_resolver import FontResolver
from src.core.library_scanner import LibraryScanner
from src.core.pipeline_runner import PipelineRunner
from src.core.renderability_service import RenderabilityService
from src.errors import FontMatchError, PipelineStoppedError
from src.models.font import FontAsset
from src.models.pipeline import (
    EpisodeContext,
    LibraryScanOutput,
    LibraryScanResult,
    PipelineConfig,
)
from src.models.renderability import RenderabilityReport, Verdict
from src.models.report import EpisodeReport, EpisodeStatus
from src.models.tool_result import ToolResult
from src.ports.filesystem import FilesystemPort
from src.ports.subprocess import SubprocessPort
from tests.unit.core.font_builders import ARABIC, FaceSpec, build_font

SCRIPT = "\n".join(
    [
        "[Script Info]",
        "ScriptType: v4.00+",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        "Style: Default,Foo,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
        "100,100,0,0,1,2,0,2,10,10,10,1",
        "Style: Ar,Bar,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
        "100,100,0,0,1,2,0,2,10,10,10,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello {\\b1}world",
        "Dialogue: 0,0:00:03.00,0:00:04.00,Ar,,0,0,0,,\u200fمرحبا\u200f",
        "",
    ]
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def fonts(tmp_path: Path) -> dict[str, Path]:
    return {
        "Foo": build_font(tmp_path, "foo.ttf", FaceSpec("Foo")),
        "Bar": build_font(tmp_path, "bar.ttf", FaceSpec("Bar", codepoints=ARABIC)),
    }


@pytest.fixture
def scan(tmp_path: Path) -> LibraryScanResult:
    episode = tmp_path / "episode.mkv"
    subtitle = tmp_path / "episode.ass"
    episode.touch()
    subtitle.write_text(SCRIPT, encoding="utf-8")
    return LibraryScanResult(
        episode_path=episode, subtitle_path=subtitle, anime_title="Show"
    )


def _resolver(mapping: dict[str, Path]) -> MagicMock:
    resolver = MagicMock(spec=FontResolver)

    async def resolve(query):  # type: ignore[no-untyped-def]
        if query.requested_name not in mapping:
            raise FontMatchError(f"no font for {query.requested_name}")
        return FontAsset(
            name=query.requested_name,
            file_path=mapping[query.requested_name],
            source="test",
            layer_found=1,
            cache_hit=True,
            nameids={},
        )

    resolver.resolve = AsyncMock(side_effect=resolve)
    resolver.for_run.return_value = resolver
    return resolver


def _runner(
    resolver: MagicMock,
    scan: LibraryScanResult,
    service: RenderabilityService | MagicMock | None,
) -> PipelineRunner:
    subprocess = MagicMock(spec=SubprocessPort)
    subprocess.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="mock",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
        )
    )
    filesystem = MagicMock(spec=FilesystemPort)
    for name in (
        "move_to_trash",
        "write_file_atomic",
        "ensure_directory",
        "replace_file",
    ):
        setattr(filesystem, name, AsyncMock())
    registry = MagicMock(spec=ToolRegistry)
    registry.is_available.return_value = True
    ingestion = MagicMock(spec=FontIngestionService)
    ingestion.ingest_directories = AsyncMock()
    ingestion.ingest_files = AsyncMock()
    scanner = MagicMock(spec=LibraryScanner)
    scanner.scan = AsyncMock(
        return_value=LibraryScanOutput(episodes=[scan], font_directories=[])
    )
    return PipelineRunner(
        font_resolver=resolver,
        subprocess_adapter=subprocess,
        filesystem=filesystem,
        tool_registry=registry,
        config=AppConfig(max_concurrent_disk_io=2),
        font_ingestion_service=ingestion,
        disk_semaphore=asyncio.Semaphore(2),
        library_scanner=scanner,
        renderability_service=service,
    )


def _real_service() -> RenderabilityService:
    return RenderabilityService(FontFaceReaderAdapter())


async def _analyse(
    runner: PipelineRunner,
    scan: LibraryScanResult,
    tmp_path: Path,
    resolver: MagicMock,
    stop_event: asyncio.Event | None = None,
) -> EpisodeContext:
    return await runner._analyze_episode(
        scan,
        "Show",
        PipelineConfig(library_path=tmp_path, dry_run=True),
        _utc_now(),
        stop_event=stop_event,
        font_resolver=resolver,
    )


# ---------------------------------------------------------------------------
# The report is produced and attached
# ---------------------------------------------------------------------------


class TestReportAttachment:
    async def test_report_attached_after_font_resolution(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        resolver = _resolver(fonts)
        runner = _runner(resolver, scan, _real_service())

        ctx = await _analyse(runner, scan, tmp_path, resolver)

        report = ctx.renderability_report
        assert isinstance(report, RenderabilityReport)
        assert report.episode_path == str(scan.episode_path)
        # Attachments mirror the planned mux, in mux order.
        assert ctx.mux_job is not None
        assert [a.attachment_filename for a in report.attachments] == [
            font.file_path.name for font in ctx.mux_job.fonts
        ]
        assert {a.attachment_filename for a in report.attachments} == {
            "foo.ttf",
            "bar.ttf",
        }
        verdicts = {
            (r.style_name, r.bold): v.verdict
            for r, v in zip(report.requirements, report.verdicts, strict=True)
        }
        assert verdicts == {
            ("Default", False): Verdict.RENDERABLE_AS_INTENDED,
            ("Default", True): Verdict.RENDERABLE_SYNTHESISED,
            ("Ar", False): Verdict.RENDERABLE_AS_INTENDED,
        }
        assert report.summary.renderable == 3
        assert report.report_timestamp is not None
        assert report.report_timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    async def test_analysis_is_advisory_and_changes_nothing_else(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        resolver = _resolver(fonts)
        with_service = await _analyse(
            _runner(resolver, scan, _real_service()), scan, tmp_path, resolver
        )
        without_service = await _analyse(
            _runner(resolver, scan, None), scan, tmp_path, resolver
        )

        assert without_service.renderability_report is None
        assert with_service.status is without_service.status is EpisodeStatus.COMPLETE
        assert with_service.errors == without_service.errors == []
        assert with_service.resolved_fonts == without_service.resolved_fonts
        assert with_service.missing_fonts == without_service.missing_fonts
        assert with_service.mux_job == without_service.mux_job
        assert with_service.mux_job is not None
        assert sorted(f.name for f in with_service.mux_job.fonts) == ["Bar", "Foo"]

    async def test_a_font_that_could_not_be_resolved_is_not_renderable(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        resolver = _resolver({"Foo": fonts["Foo"]})  # "Bar" is never found
        runner = _runner(resolver, scan, _real_service())

        ctx = await _analyse(runner, scan, tmp_path, resolver)

        assert ctx.missing_fonts == ["Bar"]
        report = ctx.renderability_report
        assert report is not None
        by_variant = {
            (r.style_name, r.bold): v.verdict
            for r, v in zip(report.requirements, report.verdicts, strict=True)
        }
        assert by_variant == {
            ("Ar", False): Verdict.NOT_RENDERABLE,
            ("Default", False): Verdict.RENDERABLE_AS_INTENDED,
            ("Default", True): Verdict.RENDERABLE_SYNTHESISED,
        }

    async def test_the_same_file_resolved_twice_is_one_attachment(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        resolver = _resolver({"Foo": fonts["Foo"], "Bar": fonts["Foo"]})
        runner = _runner(resolver, scan, _real_service())

        ctx = await _analyse(runner, scan, tmp_path, resolver)

        assert ctx.renderability_report is not None
        assert len(ctx.renderability_report.attachments) == 1

    async def test_works_in_a_dry_run_without_touching_the_filesystem_port(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        resolver = _resolver(fonts)
        runner = _runner(resolver, scan, _real_service())

        await _analyse(runner, scan, tmp_path, resolver)

        runner.filesystem.write_file_atomic.assert_not_awaited()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Failure and stop behaviour
# ---------------------------------------------------------------------------


class TestFailureAndStop:
    @pytest.mark.parametrize("error", [OSError("disk gone"), ValueError("bad data")])
    async def test_a_failing_analysis_never_fails_the_episode(
        self,
        tmp_path: Path,
        scan: LibraryScanResult,
        fonts: dict[str, Path],
        error: Exception,
    ) -> None:
        service = MagicMock(spec=RenderabilityService)
        service.analyse = AsyncMock(side_effect=error)
        resolver = _resolver(fonts)
        runner = _runner(resolver, scan, service)

        ctx = await _analyse(runner, scan, tmp_path, resolver)

        service.analyse.assert_awaited_once()
        assert ctx.renderability_report is None
        assert ctx.status is EpisodeStatus.COMPLETE
        assert ctx.errors == []
        assert ctx.mux_job is not None

    async def test_stop_before_analysis_raises_without_calling_the_service(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        service = MagicMock(spec=RenderabilityService)
        service.analyse = AsyncMock()
        resolver = _resolver(fonts)
        runner = _runner(resolver, scan, service)
        stop_event = asyncio.Event()
        ctx = EpisodeContext(
            scan_result=scan, repaired_content=SCRIPT, status=EpisodeStatus.COMPLETE
        )
        stop_event.set()

        with pytest.raises(PipelineStoppedError):
            await runner._assess_renderability(ctx, stop_event=stop_event)

        service.analyse.assert_not_awaited()

    async def test_stop_during_analysis_discards_the_result(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        stop_event = asyncio.Event()
        real = _real_service()

        async def analyse_then_stop(**kwargs):  # type: ignore[no-untyped-def]
            report = await real.analyse(**kwargs)
            stop_event.set()
            return report

        service = MagicMock(spec=RenderabilityService)
        service.analyse = AsyncMock(side_effect=analyse_then_stop)
        resolver = _resolver(fonts)
        runner = _runner(resolver, scan, service)

        with pytest.raises(PipelineStoppedError):
            await _analyse(runner, scan, tmp_path, resolver, stop_event)

    async def test_no_subtitle_content_means_no_analysis(
        self, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        service = MagicMock(spec=RenderabilityService)
        service.analyse = AsyncMock()
        runner = _runner(_resolver(fonts), scan, service)
        ctx = EpisodeContext(scan_result=scan, status=EpisodeStatus.COMPLETE)

        assert await runner._assess_renderability(ctx) is ctx
        service.analyse.assert_not_awaited()


# ---------------------------------------------------------------------------
# Surfacing through run()
# ---------------------------------------------------------------------------


class TestRunSurfacesTheReport:
    async def test_pipeline_report_carries_it_per_episode(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        resolver = _resolver(fonts)
        runner = _runner(resolver, scan, _real_service())

        report = await runner.run(PipelineConfig(library_path=tmp_path, dry_run=True))

        assert len(report.episodes) == 1
        episode = report.episodes[0]
        assert episode.renderability_report is not None
        assert episode.renderability_report.summary.total_requirements == 3
        assert episode.status is EpisodeStatus.COMPLETE

    async def test_episode_report_without_a_service_has_none(
        self, tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
    ) -> None:
        resolver = _resolver(fonts)
        runner = _runner(resolver, scan, None)

        report = await runner.run(PipelineConfig(library_path=tmp_path, dry_run=True))

        assert report.episodes[0].renderability_report is None


# ---------------------------------------------------------------------------
# Model additions
# ---------------------------------------------------------------------------


def test_episode_models_default_to_no_report() -> None:
    assert (
        EpisodeReport(
            episode_path=Path("a.mkv"), status=EpisodeStatus.SKIPPED
        ).renderability_report
        is None
    )


async def test_episode_report_round_trips_with_a_report(
    tmp_path: Path, scan: LibraryScanResult, fonts: dict[str, Path]
) -> None:
    report = await _real_service().analyse(
        episode_path=scan.episode_path,
        subtitle_content=SCRIPT,
        font_paths=list(fonts.values()),
    )
    episode = EpisodeReport(
        episode_path=scan.episode_path,
        status=EpisodeStatus.COMPLETE,
        renderability_report=report,
    )
    assert EpisodeReport.model_validate_json(episode.model_dump_json()) == episode
