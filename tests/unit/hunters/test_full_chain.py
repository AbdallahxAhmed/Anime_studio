from unittest.mock import MagicMock

from src.hunters.registry import HunterRegistry
from src.hunters.sources.mkv_extract import MkvExtractHunter
from src.hunters.sources.sibling_font import SiblingFontHunter
from src.hunters.system_font_hunter import SystemFontHunter
from src.hunters.sources.google_fonts import GoogleFontsHunter
from src.hunters.sources.fontsquirrel import FontSquirrelHunter
from src.hunters.sources.dafont import DaFontHunter
from src.hunters.sources.fontspace import FontSpaceHunter
from src.hunters.sources.befonts import BeFontsHunter
from src.hunters.sources.arabic_fonts import ArabicFontsHunter
from src.hunters.sources.search_engine import SearchEngineHunter


def test_hunter_registry_priority_order() -> None:
    registry = HunterRegistry()
    subprocess_port = MagicMock()

    # Register in arbitrary order
    registry.register(SearchEngineHunter())
    registry.register(SystemFontHunter())
    registry.register(SiblingFontHunter())
    registry.register(MkvExtractHunter(subprocess_port))
    registry.register(GoogleFontsHunter())
    registry.register(FontSquirrelHunter())
    registry.register(DaFontHunter())
    registry.register(FontSpaceHunter())
    registry.register(BeFontsHunter())
    registry.register(ArabicFontsHunter())

    hunters = list(registry.iter_hunters())
    assert len(hunters) == 10

    # Verify priority order (1 -> 2 -> 3 -> 4 -> ... -> 5)
    priorities = [h.priority for h in hunters]
    assert priorities == [1, 2, 3, 4, 4, 4, 4, 4, 4, 5]

    # Verify exact classes mapping to layers
    assert isinstance(hunters[0], MkvExtractHunter)
    assert isinstance(hunters[1], SiblingFontHunter)
    assert isinstance(hunters[2], SystemFontHunter)
    for h in hunters[3:9]:
        assert h.priority == 4
    assert isinstance(hunters[9], SearchEngineHunter)


def test_circuit_breaker_isolation() -> None:
    registry = HunterRegistry(cooldown_s=60.0)

    h1 = GoogleFontsHunter()
    h2 = DaFontHunter()

    registry.register(h1)
    registry.register(h2)

    cb1 = registry.get_circuit(h1.name)
    cb2 = registry.get_circuit(h2.name)

    # Trip cb1
    cb1.record_failure()
    cb1.record_failure()
    cb1.record_failure()

    assert cb1.can_execute() is False
    assert cb2.can_execute() is True
