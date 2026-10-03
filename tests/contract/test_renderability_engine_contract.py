"""Contract tests for the renderability engine (Feature 013).

Two kinds of guarantee are pinned here, independent of any one implementation
detail:

* **Architecture** (Constitution Principle I): the new core modules are pure and
  depend only on ``src.models`` and ``src.ports``.
* **Behaviour** of the report the engine returns: every verdict is reachable,
  facts and dispositions stay separate (R7), every timestamp is UTC (R8), a
  filename is never identity (R6), the verdicts do not depend on attachment
  order, and the engine never raises on arbitrary well-typed input.
"""

from __future__ import annotations

import ast
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.core.renderability_engine import RENDERABLE_VERDICTS, RenderabilityEngine
from src.models.renderability import (
    Attachment,
    AttachmentFace,
    CodepointRange,
    Environment,
    FaceNameRecord,
    RenderabilityReport,
    Requirement,
    Style,
    Verdict,
)

SRC = Path(__file__).resolve().parents[2] / "src"

# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------

PURE_MODULES = (
    "codepoint_ranges",
    "style_resolution",
    "renderability_engine",
    "subtitle_requirements",
)
SERVICE_MODULES = ("renderability_service",)
ALLOWED_INTERNAL = {
    "src.core.codepoint_ranges",
    "src.core.style_resolution",
    "src.core.renderability_engine",
    "src.core.subtitle_requirements",
}


def _imports(module: str) -> set[str]:
    """Return the modules imported by ``src/core/<module>.py`` as module paths."""
    tree = ast.parse((SRC / "core" / f"{module}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{module}: relative import"
            if not node.module:
                continue
            for alias in node.names:
                submodule = f"{node.module}.{alias.name}"
                is_module = (
                    SRC.parent / (submodule.replace(".", "/") + ".py")
                ).is_file()
                found.add(submodule if is_module else node.module)
    return found


@pytest.mark.parametrize("module", PURE_MODULES + SERVICE_MODULES)
def test_new_core_modules_import_only_models_ports_and_each_other(module: str) -> None:
    internal = {name for name in _imports(module) if name.startswith("src.")}
    disallowed = {
        name
        for name in internal
        if not (
            name.startswith(("src.models", "src.ports"))
            or name in ALLOWED_INTERNAL
            or name == "src.core.renderability_service"
        )
    }
    assert not disallowed, (
        f"{module} reaches outside models/ports: {sorted(disallowed)}"
    )


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_modules_never_touch_ports_io_or_the_clock_directly(module: str) -> None:
    imports = _imports(module)
    assert not {n for n in imports if n.startswith("src.ports")}, (
        "pure module uses a port"
    )
    for forbidden in ("asyncio", "subprocess", "socket", "shutil", "tempfile", "os"):
        assert forbidden not in imports, f"{module} imports {forbidden}"
    assert "pathlib" not in imports, f"{module} imports pathlib"
    assert "open" not in {
        node.func.id
        for node in ast.walk(
            ast.parse((SRC / "core" / f"{module}.py").read_text(encoding="utf-8"))
        )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }, f"{module} calls open()"


def test_models_do_not_import_the_new_core_modules() -> None:
    for path in (SRC / "models").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert not any(
                n.startswith(("src.core", "src.adapters", "src.gui")) for n in names
            ), path


def test_engine_has_no_port_because_it_has_no_io_boundary() -> None:
    """Constitution XII: no interface for a single pure implementation."""
    assert not (SRC / "ports" / "renderability_engine.py").exists()


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _name(name_id: int, value: str, platform: int = 3) -> FaceNameRecord:
    return FaceNameRecord(
        name_id=name_id,
        platform_id=platform,
        encoding_id=1,
        language_id=0x409,
        value=value,
    )


def _face(
    index: int,
    family: str,
    cmap: Sequence[tuple[int, int]],
    *,
    weight: int | None = 400,
    slant: str | None = None,
    reason: str | None = None,
) -> AttachmentFace:
    return AttachmentFace(
        face_index=index,
        name_records=[_name(1, family)] if family else [],
        cmap_ranges=[CodepointRange(start=a, end=b) for a, b in cmap],
        weight=weight,
        slant=slant,
        unverifiable_reason=reason,
    )


def _attachment(
    attachment_id: int, *faces: AttachmentFace, name: str = "f.ttf"
) -> Attachment:
    return Attachment(
        attachment_id=attachment_id,
        attachment_filename=name,
        mime_type="font/ttf",
        faces=list(faces),
    )


def _req(
    font: str,
    ranges: Sequence[tuple[int, int]] = ((0x41, 0x43),),
    *,
    bold: bool = False,
    italic: bool = False,
    style: str = "Default",
) -> Requirement:
    return Requirement(
        track_id=0,
        style_name=style,
        font_name=font,
        bold=bold,
        italic=italic,
        codepoint_ranges=[CodepointRange(start=a, end=b) for a, b in ranges],
    )


LATIN = ((0x41, 0x5A), (0x61, 0x7A))
ARABIC = ((0x0627, 0x064A),)

# ---------------------------------------------------------------------------
# Behaviour: every verdict is reachable
# ---------------------------------------------------------------------------


def _scenario(
    verdict: Verdict, family: str, base_id: int
) -> tuple[list[Attachment], Requirement]:
    """Attachments and one requirement that must produce *verdict*."""
    plain = _attachment(base_id, _face(0, family, LATIN))
    match verdict:
        case Verdict.RENDERABLE_AS_INTENDED:
            return [plain], _req(family)
        case Verdict.RENDERABLE_SYNTHESISED:
            return [plain], _req(family, bold=True)
        case Verdict.RENDERABLE_VIA_FALLBACK:
            return [plain], _req(family, ((0x41, 0x43), (0x266A, 0x266A)))
        case Verdict.AMBIGUOUS:
            return (
                [plain, _attachment(base_id + 1, _face(0, family, LATIN + ARABIC))],
                _req(family, ((0x41, 0x43), (0x0627, 0x0627))),
            )
        case Verdict.NOT_RENDERABLE:
            return [_attachment(base_id, _face(0, f"{family}-other", LATIN))], _req(
                family
            )
        case Verdict.UNVERIFIABLE:
            broken = _face(0, "", (), weight=None, reason="truncated")
            return [_attachment(base_id, broken)], _req(family)
    raise AssertionError(verdict)  # pragma: no cover


SCENARIOS: dict[Verdict, tuple[list[Attachment], Requirement]] = {
    verdict: _scenario(verdict, "Foo", 1) for verdict in Verdict
}


def test_scenarios_cover_the_whole_verdict_enum() -> None:
    assert set(SCENARIOS) == set(Verdict)


@pytest.mark.parametrize("expected", list(Verdict), ids=lambda v: v.value)
def test_every_verdict_is_reachable(expected: Verdict) -> None:
    attachments, requirement = SCENARIOS[expected]
    report = RenderabilityEngine().evaluate(
        attachments=attachments, requirements=[requirement]
    )
    assert [v.verdict for v in report.verdicts] == [expected]
    assert report.verdicts[0].reason


def test_renderable_verdicts_are_exactly_the_three_renderable_members() -> None:
    assert {
        v for v in Verdict if v.value.startswith("renderable_")
    } == RENDERABLE_VERDICTS


def test_absence_is_never_asserted_while_any_face_is_unreadable() -> None:
    """The one scenario that cannot coexist with NOT_RENDERABLE in a container."""
    attachments, requirement = _scenario(Verdict.NOT_RENDERABLE, "Foo", 1)
    broken, _ = _scenario(Verdict.UNVERIFIABLE, "Other", 2)
    report = RenderabilityEngine().evaluate(
        attachments=[*attachments, *broken], requirements=[requirement]
    )
    assert report.verdicts[0].verdict is Verdict.UNVERIFIABLE


# ---------------------------------------------------------------------------
# Behaviour: report guarantees
# ---------------------------------------------------------------------------

READABLE_VERDICTS = tuple(v for v in Verdict if v is not Verdict.UNVERIFIABLE)


def _report_for_every_readable_scenario() -> RenderabilityReport:
    """One container holding a scenario per verdict that needs a readable container."""
    attachments: list[Attachment] = []
    requirements: list[Requirement] = []
    for number, verdict in enumerate(READABLE_VERDICTS):
        atts, requirement = _scenario(verdict, f"Family{number}", 10 * number + 1)
        attachments.extend(atts)
        requirements.append(
            requirement.model_copy(update={"style_name": verdict.value})
        )
    return RenderabilityEngine().evaluate(
        episode_path="/lib/ep.mkv",
        attachments=attachments,
        styles=[Style(name="Default", font_name="Family0", track_id=0)],
        requirements=requirements,
    )


def test_report_is_complete_and_round_trips() -> None:
    report = _report_for_every_readable_scenario()
    assert {v.verdict for v in report.verdicts} == set(READABLE_VERDICTS)
    assert report.report_schema_version == "1.0.0"
    assert report.report_timestamp is not None
    assert report.provenance
    assert RenderabilityReport.model_validate_json(report.model_dump_json()) == report
    assert set(report.model_dump()) == set(RenderabilityReport.model_fields)


def test_r7_facts_and_dispositions_stay_separate() -> None:
    report = _report_for_every_readable_scenario()
    assert all(v.disposition is None for v in report.verdicts)


def test_r8_every_timestamp_is_utc() -> None:
    report = _report_for_every_readable_scenario()
    stamps = [p.timestamp for p in report.provenance]
    assert report.report_timestamp is not None
    for stamp in (report.report_timestamp, *stamps):
        assert stamp.utcoffset() == timedelta(0)
    dumped = report.model_dump(mode="json")
    assert dumped["report_timestamp"].endswith("Z")
    assert all(entry["timestamp"].endswith("Z") for entry in dumped["provenance"])


def test_summary_is_consistent_with_the_verdicts() -> None:
    report = _report_for_every_readable_scenario()
    kinds = [v.verdict for v in report.verdicts]
    summary = report.summary
    assert summary.total_requirements == len(report.requirements) == len(kinds)
    assert summary.renderable == sum(k in RENDERABLE_VERDICTS for k in kinds)
    assert summary.not_renderable == kinds.count(Verdict.NOT_RENDERABLE)
    assert summary.unverifiable == kinds.count(Verdict.UNVERIFIABLE)
    assert summary.ambiguous == kinds.count(Verdict.AMBIGUOUS)
    assert summary.total_styles == len(report.styles)


def test_the_engine_is_pure_and_deterministic() -> None:
    attachments, requirement = SCENARIOS[Verdict.RENDERABLE_AS_INTENDED]
    clock_time = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    environment = Environment(fonttools_version="x", python_version="y", platform="z")
    outputs = [
        RenderabilityEngine(clock=lambda: clock_time, environment=environment).evaluate(
            attachments=attachments, requirements=[requirement]
        )
        for _ in range(3)
    ]
    assert outputs[0] == outputs[1] == outputs[2]


# ---------------------------------------------------------------------------
# Behaviour: invariances and robustness over random inputs
# ---------------------------------------------------------------------------

FAMILIES = ("Foo", "Bar", "Baz")
CODEPOINT_POOL = (
    (0x41, 0x5A),
    (0x61, 0x7A),
    (0x30, 0x39),
    (0x20, 0x20),
    (0x0627, 0x064A),
    (0x266A, 0x266A),
    (0xE000, 0xE0FF),
    (0x3040, 0x309F),
)


def _random_ranges(
    rng: random.Random, *, allow_bad: bool = False
) -> list[tuple[int, int]]:
    chosen: list[tuple[int, int]] = []
    for low, high in rng.sample(CODEPOINT_POOL, rng.randint(0, 4)):
        start = rng.randint(low, high)
        chosen.append((start, rng.randint(start, high)))
    if allow_bad and rng.random() < 0.1:
        chosen.append((rng.randint(10, 50), rng.randint(0, 9)))  # inverted
    return chosen


def _random_world(
    rng: random.Random,
) -> tuple[list[Attachment], list[Requirement], list[Style]]:
    attachments: list[Attachment] = []
    for attachment_id in range(1, rng.randint(0, 5) + 1):
        faces = [
            _face(
                face_index,
                rng.choice(FAMILIES + ("",)),
                _random_ranges(rng),
                weight=rng.choice((None, 400, 700, 300, 900, 5, 7)),
                slant=rng.choice((None, "italic", "oblique")),
                reason="broken" if rng.random() < 0.1 else None,
            )
            for face_index in range(rng.randint(0, 3))
        ]
        attachments.append(
            _attachment(attachment_id, *faces, name=f"{rng.random()}.ttf")
        )
    requirements = [
        _req(
            rng.choice(FAMILIES + ("Nope", "")),
            _random_ranges(rng, allow_bad=True),
            bold=rng.random() < 0.4,
            italic=rng.random() < 0.3,
            style=rng.choice(("Default", "Sign", "Gone")),
        )
        for _ in range(rng.randint(0, 6))
    ]
    styles = [
        Style(
            name=name,
            font_name=rng.choice(FAMILIES),
            bold=rng.random() < 0.3,
            track_id=0,
        )
        for name in rng.sample(("Default", "Sign"), rng.randint(0, 2))
    ]
    return attachments, requirements, styles


SEEDS = range(300)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_fuzz_never_raises_and_always_yields_a_consistent_report(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(75):
        attachments, requirements, styles = _random_world(rng)
        report = RenderabilityEngine().evaluate(
            attachments=attachments, requirements=requirements, styles=styles
        )
        assert len(report.verdicts) == len(requirements)
        assert all(v.disposition is None and v.reason for v in report.verdicts)
        summary = report.summary
        assert (
            summary.renderable
            + summary.not_renderable
            + summary.unverifiable
            + summary.ambiguous
            == len(requirements)
        )
        assert (
            RenderabilityReport.model_validate_json(report.model_dump_json()) == report
        )


def test_filenames_never_change_a_verdict() -> None:
    """R6: identity comes from name records, never from the filename."""
    for seed in SEEDS:
        rng = random.Random(seed)
        attachments, requirements, styles = _random_world(rng)
        baseline = RenderabilityEngine().evaluate(
            attachments=attachments, requirements=requirements, styles=styles
        )
        renamed = [
            a.model_copy(update={"attachment_filename": rng.choice(FAMILIES) + ".ttf"})
            for a in attachments
        ]
        again = RenderabilityEngine().evaluate(
            attachments=renamed, requirements=requirements, styles=styles
        )
        assert [v.model_dump() for v in again.verdicts] == [
            v.model_dump() for v in baseline.verdicts
        ], seed


def test_verdicts_do_not_depend_on_attachment_order() -> None:
    """Ties are either harmless (same verdict) or AMBIGUOUS, never order-dependent."""
    for seed in SEEDS:
        rng = random.Random(seed)
        attachments, requirements, styles = _random_world(rng)
        shuffled = list(attachments)
        rng.shuffle(shuffled)
        first = RenderabilityEngine().evaluate(
            attachments=attachments, requirements=requirements, styles=styles
        )
        second = RenderabilityEngine().evaluate(
            attachments=shuffled, requirements=requirements, styles=styles
        )
        assert [v.verdict for v in first.verdicts] == [
            v.verdict for v in second.verdicts
        ], seed


def test_adding_an_unrelated_family_never_changes_a_verdict() -> None:
    """A font that matches nobody's name cannot rescue or break anyone (R5)."""
    for seed in SEEDS:
        rng = random.Random(seed)
        attachments, requirements, styles = _random_world(rng)
        requirements = [
            r for r in requirements if r.font_name in FAMILIES + ("Nope", "")
        ]
        baseline = RenderabilityEngine().evaluate(
            attachments=attachments, requirements=requirements, styles=styles
        )
        extra = _attachment(
            99,
            _face(0, "UnrelatedFamily", ((0, 0x10FFFF),), weight=400),
            name="Foo.ttf",
        )
        with_extra = RenderabilityEngine().evaluate(
            attachments=[*attachments, extra], requirements=requirements, styles=styles
        )
        assert [v.verdict for v in with_extra.verdicts] == [
            v.verdict for v in baseline.verdicts
        ], seed
