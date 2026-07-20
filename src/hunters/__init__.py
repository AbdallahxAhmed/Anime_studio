"""Font hunters registry and implementations."""

from src.hunters.registry import HunterRegistry
from src.hunters.system_font_hunter import SystemFontHunter
from src.hunters.sources.mkv_extract import MkvExtractHunter
from src.hunters.sources.sibling_font import SiblingFontHunter
from src.hunters.sources.google_fonts import GoogleFontsHunter
from src.hunters.sources.fontsquirrel import FontSquirrelHunter
from src.hunters.sources.dafont import DaFontHunter
from src.hunters.sources.fontspace import FontSpaceHunter
from src.hunters.sources.befonts import BeFontsHunter
from src.hunters.sources.arabic_fonts import ArabicFontsHunter
from src.hunters.sources.search_engine import SearchEngineHunter

__all__ = [
    "HunterRegistry",
    "SystemFontHunter",
    "MkvExtractHunter",
    "SiblingFontHunter",
    "GoogleFontsHunter",
    "FontSquirrelHunter",
    "DaFontHunter",
    "FontSpaceHunter",
    "BeFontsHunter",
    "ArabicFontsHunter",
    "SearchEngineHunter",
]
