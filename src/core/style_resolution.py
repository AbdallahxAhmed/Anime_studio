"""ASS style lookup rules shared by the extractor and the engine.

Pure (Constitution Principle I).  Mirrors libass ``ass_lookup_style``
(``libass/ass_utils.c``, verified against libass master ``f61db567``):

* leading ``*`` characters are ignored;
* ``Default`` is matched case-insensitively, every other name exactly;
* when a name is declared more than once, the **last** declaration wins.

When a name is not declared, libass falls back to the style named ``Default``
or, if the file declares none, to its built-in ``Default`` style whose font is
Arial.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from src.models.renderability import Style

DEFAULT_STYLE_NAME: Final[str] = "Default"
BUILTIN_DEFAULT_FONT: Final[str] = "Arial"
"""Font of libass's built-in ``Default`` style (``set_default_style``)."""


def normalise_style_name(name: str) -> str:
    """Return the name libass actually looks up."""
    wanted = name.strip().lstrip("*")
    if wanted.lower() == DEFAULT_STYLE_NAME.lower() and wanted.isascii():
        return DEFAULT_STYLE_NAME
    return wanted


def lookup_style(styles: Sequence[Style], name: str) -> Style | None:
    """Find the declared style libass would pick for *name*, or ``None``."""
    wanted = normalise_style_name(name)
    for style in reversed(styles):
        if style.name.strip() == wanted:
            return style
    return None


def clean_font_name(name: str) -> str:
    """Strip whitespace and the vertical-writing ``@`` prefix from a font name."""
    cleaned = name.strip()
    if cleaned.startswith("@"):
        cleaned = cleaned[1:].strip()
    return cleaned
