"""Unit tests for the pure codepoint-range helpers."""

from __future__ import annotations

import pytest

from src.core import codepoint_ranges as cr
from src.models.renderability import CodepointRange

# ── normalise / conversion ────────────────────────────────────────────


class TestNormalise:
    def test_sorts_and_merges_overlapping_and_adjacent(self) -> None:
        assert cr.normalise([(10, 12), (1, 3), (4, 5), (11, 20)]) == [(1, 5), (10, 20)]

    def test_keeps_gap_of_one_separate(self) -> None:
        assert cr.normalise([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]

    def test_empty(self) -> None:
        assert cr.normalise([]) == []

    @pytest.mark.parametrize(
        "bad",
        [(5, 1), (-1, 3), (0, cr.MAX_CODEPOINT + 1)],
    )
    def test_rejects_invalid_ranges(self, bad: tuple[int, int]) -> None:
        with pytest.raises(ValueError, match="invalid codepoint range"):
            cr.normalise([bad])

    def test_from_models_and_back(self) -> None:
        models = [CodepointRange(start=65, end=67), CodepointRange(start=68, end=70)]
        assert cr.from_models(models) == [(65, 70)]
        assert cr.to_models([(65, 70)]) == [CodepointRange(start=65, end=70)]

    def test_from_models_rejects_inverted_model(self) -> None:
        with pytest.raises(ValueError):
            cr.from_models([CodepointRange(start=10, end=2)])

    def test_from_codepoints_compacts(self) -> None:
        assert cr.from_codepoints([5, 3, 4, 9, 3]) == [(3, 5), (9, 9)]


# ── set algebra ───────────────────────────────────────────────────────


class TestAlgebra:
    def test_union(self) -> None:
        assert cr.union([(1, 3)], [(4, 6), (10, 11)]) == [(1, 6), (10, 11)]

    def test_intersect(self) -> None:
        assert cr.intersect([(1, 10), (20, 30)], [(5, 25)]) == [(5, 10), (20, 25)]

    def test_intersect_disjoint(self) -> None:
        assert cr.intersect([(1, 2)], [(5, 6)]) == []

    def test_subtract_splits_ranges(self) -> None:
        assert cr.subtract([(1, 10)], [(3, 4), (7, 7)]) == [(1, 2), (5, 6), (8, 10)]

    def test_subtract_everything(self) -> None:
        assert cr.subtract([(1, 5)], [(0, 9)]) == []

    def test_subtract_nothing(self) -> None:
        assert cr.subtract([(1, 5)], []) == [(1, 5)]

    def test_subtract_multiple_source_ranges(self) -> None:
        assert cr.subtract([(1, 3), (10, 14)], [(2, 11)]) == [(1, 1), (12, 14)]

    def test_count(self) -> None:
        assert cr.count([(1, 3), (10, 10)]) == 4
        assert cr.count([]) == 0

    @pytest.mark.parametrize(
        ("codepoint", "expected"),
        [(0, False), (1, True), (3, True), (4, False), (9, False), (10, True)],
    )
    def test_contains(self, codepoint: int, expected: bool) -> None:
        assert cr.contains([(1, 3), (10, 12)], codepoint) is expected

    def test_iter_codepoints(self) -> None:
        assert list(cr.iter_codepoints([(1, 2), (5, 5)])) == [1, 2, 5]

    def test_format_codepoints_limits_and_reports_remainder(self) -> None:
        text = cr.format_codepoints([(0x41, 0x4F)], limit=3)
        assert text == "U+0041, U+0042, U+0043 (+12 more)"

    def test_format_codepoints_without_remainder(self) -> None:
        assert cr.format_codepoints([(0x41, 0x42)]) == "U+0041, U+0042"

    def test_set_identity_subtract_then_union_restores(self) -> None:
        a = [(1, 50), (70, 90)]
        b = [(10, 20), (80, 200)]
        restored = cr.union(cr.subtract(a, b), cr.intersect(a, b))
        assert restored == a


# ── PUA ───────────────────────────────────────────────────────────────


class TestPua:
    def test_bmp_pua_boundaries(self) -> None:
        assert cr.is_pua_only([(0xE000, 0xF8FF)])
        assert not cr.is_pua_only([(0xDFFF, 0xE000)])
        assert not cr.is_pua_only([(0xF8FF, 0xF900)])

    def test_supplementary_planes(self) -> None:
        assert cr.is_pua_only([(0xF0000, 0xFFFFD)])
        assert cr.is_pua_only([(0x100000, 0x10FFFD)])
        # U+FFFFE/U+FFFFF are noncharacters, not private use.
        assert not cr.is_pua_only([(0xFFFFE, 0xFFFFF)])

    def test_mixed_is_not_pua_only(self) -> None:
        assert not cr.is_pua_only([(0x41, 0x41), (0xE000, 0xE001)])

    def test_empty_is_not_pua_only(self) -> None:
        assert not cr.is_pua_only([])

    def test_parts(self) -> None:
        mixed = [(0x41, 0x42), (0xE000, 0xE001)]
        assert cr.pua_part(mixed) == [(0xE000, 0xE001)]
        assert cr.non_pua_part(mixed) == [(0x41, 0x42)]


# ── ignorable codepoints ──────────────────────────────────────────────


class TestIgnorable:
    @pytest.mark.parametrize(
        "codepoint",
        [
            0x0009,  # tab (Cc)
            0x00AD,  # soft hyphen (Cf)
            0x200B,  # zero width space (Cf)
            0x200C,  # ZWNJ (Cf)
            0x200D,  # ZWJ (Cf)
            0x200E,  # LRM (Cf)
            0x200F,  # RLM (Cf)
            0x2028,  # line separator (Zl)
            0x2029,  # paragraph separator (Zp)
            0xFE0F,  # variation selector-16
            0xE0100,  # variation selector-17
            0xFEFF,  # BOM / ZWNBSP (Cf)
        ],
    )
    def test_is_ignorable(self, codepoint: int) -> None:
        assert cr.is_ignorable(codepoint)

    @pytest.mark.parametrize(
        "codepoint",
        [0x20, 0x41, 0x00A0, 0x0627, 0x064E, 0x266A, 0x4E00, 0xE000],
    )
    def test_is_not_ignorable(self, codepoint: int) -> None:
        assert not cr.is_ignorable(codepoint)

    def test_strip_ignorable_splits_ranges(self) -> None:
        # U+0008 (Cc) .. U+000B: tab/LF/VT are Cc → only U+0020.. survives
        assert cr.strip_ignorable([(0x41, 0x43), (0x200B, 0x200F)]) == [(0x41, 0x43)]

    def test_strip_ignorable_interior(self) -> None:
        assert cr.strip_ignorable([(0x200C, 0x200E)]) == []
        assert cr.strip_ignorable([(0xAC, 0xAE)]) == [(0xAC, 0xAC), (0xAE, 0xAE)]


# ── complex shaping ───────────────────────────────────────────────────


class TestComplexShaping:
    @pytest.mark.parametrize(
        "codepoint",
        [0x0627, 0x0645, 0xFEFB, 0x0915, 0x0E01, 0x1000, 0x1780, 0x0F40],
    )
    def test_complex_scripts_flagged(self, codepoint: int) -> None:
        assert cr.requires_complex_shaping([(codepoint, codepoint)])

    @pytest.mark.parametrize("codepoint", [0x41, 0x3042, 0x4E00, 0xAC00, 0x0410])
    def test_simple_scripts_not_flagged(self, codepoint: int) -> None:
        assert not cr.requires_complex_shaping([(codepoint, codepoint)])
