"""Pure codepoint-range algebra and Unicode classification helpers.

Shared by the renderability engine and the subtitle requirement extractor.
Everything here is I/O-free (Constitution Principle I).

A *range* is an inclusive ``(start, end)`` pair of Unicode codepoints.  A
*normalised* range list is sorted, non-overlapping, and non-adjacent; every
function that takes range lists expects normalised input and returns
normalised output.  Use :func:`normalise` / :func:`from_models` /
:func:`from_codepoints` to build them from untrusted input.
"""

from __future__ import annotations

import unicodedata
from bisect import bisect_right
from collections.abc import Iterable, Iterator, Sequence
from typing import Final, TypeAlias

from src.models.renderability import CodepointRange

Range: TypeAlias = tuple[int, int]

MAX_CODEPOINT: Final[int] = 0x10FFFF


def _fmt(codepoint: int) -> str:
    return f"U+{codepoint:04X}" if codepoint >= 0 else str(codepoint)


# ---------------------------------------------------------------------------
# Construction and conversion
# ---------------------------------------------------------------------------


def normalise(ranges: Iterable[Range]) -> list[Range]:
    """Validate, sort, and merge overlapping or adjacent ranges.

    Raises
    ------
    ValueError
        If any range is inverted (``start > end``) or lies outside
        ``U+0000..U+10FFFF``.
    """
    merged: list[Range] = []
    for start, end in sorted(ranges):
        if start < 0 or end > MAX_CODEPOINT or start > end:
            raise ValueError(f"invalid codepoint range {_fmt(start)}..{_fmt(end)}")
        if merged and start <= merged[-1][1] + 1:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def from_models(ranges: Iterable[CodepointRange]) -> list[Range]:
    """Normalise :class:`CodepointRange` models (``ValueError`` if malformed)."""
    return normalise((r.start, r.end) for r in ranges)


def from_codepoints(codepoints: Iterable[int]) -> list[Range]:
    """Normalise individual codepoints (``ValueError`` if out of range)."""
    return normalise((cp, cp) for cp in codepoints)


def to_models(ranges: Iterable[Range]) -> list[CodepointRange]:
    """Convert normalised ranges to :class:`CodepointRange` models."""
    return [CodepointRange(start=start, end=end) for start, end in ranges]


# ---------------------------------------------------------------------------
# Set algebra
# ---------------------------------------------------------------------------


def union(a: Sequence[Range], b: Sequence[Range]) -> list[Range]:
    """Return ``a ∪ b``."""
    return normalise([*a, *b])


def intersect(a: Sequence[Range], b: Sequence[Range]) -> list[Range]:
    """Return ``a ∩ b``."""
    result: list[Range] = []
    i = j = 0
    while i < len(a) and j < len(b):
        low = max(a[i][0], b[j][0])
        high = min(a[i][1], b[j][1])
        if low <= high:
            result.append((low, high))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return result


def subtract(a: Sequence[Range], b: Sequence[Range]) -> list[Range]:
    """Return ``a \\ b``."""
    result: list[Range] = []
    j = 0
    for start, end in a:
        cursor = start
        while j < len(b) and b[j][1] < cursor:
            j += 1
        k = j
        while k < len(b) and b[k][0] <= end:
            b_start, b_end = b[k]
            if b_start > cursor:
                result.append((cursor, b_start - 1))
            cursor = max(cursor, b_end + 1)
            if cursor > end:
                break
            k += 1
        if cursor <= end:
            result.append((cursor, end))
    return result


def count(ranges: Sequence[Range]) -> int:
    """Return the number of codepoints covered."""
    return sum(end - start + 1 for start, end in ranges)


def contains(ranges: Sequence[Range], codepoint: int) -> bool:
    """Return whether *codepoint* lies inside any range."""
    index = bisect_right(ranges, (codepoint, MAX_CODEPOINT)) - 1
    return index >= 0 and ranges[index][0] <= codepoint <= ranges[index][1]


def iter_codepoints(ranges: Sequence[Range]) -> Iterator[int]:
    """Yield every covered codepoint in ascending order."""
    for start, end in ranges:
        yield from range(start, end + 1)


def format_codepoints(ranges: Sequence[Range], limit: int = 8) -> str:
    """Render the first *limit* codepoints as ``U+XXXX`` plus a remainder note."""
    listed: list[str] = []
    for codepoint in iter_codepoints(ranges):
        if len(listed) == limit:
            break
        listed.append(_fmt(codepoint))
    text = ", ".join(listed)
    remainder = count(ranges) - len(listed)
    return f"{text} (+{remainder} more)" if remainder > 0 else text


# ---------------------------------------------------------------------------
# Unicode classification
# ---------------------------------------------------------------------------

PUA_RANGES: Final[tuple[Range, ...]] = (
    (0xE000, 0xF8FF),
    (0xF0000, 0xFFFFD),
    (0x100000, 0x10FFFD),
)
"""Unicode private-use areas (BMP, plane 15, plane 16)."""


def pua_part(ranges: Sequence[Range]) -> list[Range]:
    """Return the private-use portion of *ranges*."""
    return intersect(ranges, PUA_RANGES)


def non_pua_part(ranges: Sequence[Range]) -> list[Range]:
    """Return the portion of *ranges* outside the private-use areas."""
    return subtract(ranges, PUA_RANGES)


def is_pua_only(ranges: Sequence[Range]) -> bool:
    """Return whether *ranges* is non-empty and lies entirely in private-use areas."""
    return bool(ranges) and not non_pua_part(ranges)


_VARIATION_SELECTORS: Final[tuple[Range, ...]] = ((0xFE00, 0xFE0F), (0xE0100, 0xE01EF))
_IGNORABLE_CATEGORIES: Final[frozenset[str]] = frozenset({"Cc", "Cf", "Zl", "Zp"})


def is_ignorable(codepoint: int) -> bool:
    """Return whether a font is not expected to carry a glyph for *codepoint*.

    Covers control characters (Cc), format characters such as zero-width
    joiners, bidi marks and the soft hyphen (Cf), line and paragraph
    separators (Zl/Zp), and variation selectors.  The renderer skips or
    shapes these without a cmap entry, so their absence is never a missing
    glyph.  Ordinary spaces (Zs) are **not** ignorable: they are rendered
    through the font.
    """
    if contains(_VARIATION_SELECTORS, codepoint):
        return True
    return unicodedata.category(chr(codepoint)) in _IGNORABLE_CATEGORIES


def strip_ignorable(ranges: Sequence[Range]) -> list[Range]:
    """Return *ranges* with every ignorable codepoint removed."""
    kept: list[Range] = []
    for start, end in ranges:
        run_start: int | None = None
        for codepoint in range(start, end + 1):
            if is_ignorable(codepoint):
                if run_start is not None:
                    kept.append((run_start, codepoint - 1))
                    run_start = None
            elif run_start is None:
                run_start = codepoint
        if run_start is not None:
            kept.append((run_start, end))
    return normalise(kept)


_CRITICAL_SPECIAL_CATEGORIES: Final[frozenset[str]] = frozenset({"Co", "Cn", "Cs"})


def is_critical(codepoint: int) -> bool:
    """Return whether losing the glyph for *codepoint* loses part of the message.

    Letters, marks and numbers (L*, M*, N*) carry the text.  So do private-use
    codepoints (Co), whose meaning only the named font defines, and unassigned
    or surrogate codepoints (Cn, Cs), which cannot be judged decorative.
    Punctuation, symbols and spaces (P*, S*, Z*) are treated as decorative: a
    missing glyph degrades the look of a line but not its wording.
    """
    category = unicodedata.category(chr(codepoint))
    return category[0] in "LMN" or category in _CRITICAL_SPECIAL_CATEGORIES


def split_critical(ranges: Sequence[Range]) -> tuple[list[Range], list[Range]]:
    """Split *ranges* into ``(critical, decorative)`` codepoint ranges."""
    critical: list[Range] = []
    decorative: list[Range] = []
    for codepoint in iter_codepoints(ranges):
        target = critical if is_critical(codepoint) else decorative
        target.append((codepoint, codepoint))
    return normalise(critical), normalise(decorative)


COMPLEX_SHAPING_RANGES: Final[tuple[Range, ...]] = tuple(
    normalise(
        [
            (0x0600, 0x07BF),  # Arabic, Syriac, Arabic Supplement, Thaana
            (0x07C0, 0x07FF),  # NKo
            (0x0840, 0x089F),  # Mandaic, Syriac Supplement, Arabic Extended-B
            (0x08A0, 0x08FF),  # Arabic Extended-A
            (0x0900, 0x0DFF),  # Devanagari through Sinhala (Indic scripts)
            (0x0E00, 0x0EFF),  # Thai, Lao
            (0x0F00, 0x0FFF),  # Tibetan
            (0x1000, 0x109F),  # Myanmar
            (0x1780, 0x17FF),  # Khmer
            (0x1800, 0x18AF),  # Mongolian
            (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
            (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
        ]
    )
)
"""Scripts whose correct rendering depends on OpenType shaping, not just cmap."""


def requires_complex_shaping(ranges: Sequence[Range]) -> bool:
    """Return whether *ranges* touches a script that needs OpenType shaping."""
    return bool(intersect(ranges, COMPLEX_SHAPING_RANGES))
