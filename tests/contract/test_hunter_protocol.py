from src.ports.font_hunter import HunterProtocol
from src.models.font import FontQuery, FontPayload, HunterResult
from src.hunters.system_font_hunter import SystemFontHunter

# Note: These tests are written test-first and will fail until HunterProtocol is implemented.


class ConformingHunter:
    def __init__(self):
        self.name: str = "Conforming"
        self.priority: int = 1
        self.rate_limit: float = 1.5
        self.circuit_breaker_threshold: int = 3
        self.ping_url: str | None = "http://example.com/ping"

    def supports(self, query: FontQuery) -> bool:
        return True

    async def search(self, query: FontQuery) -> list[HunterResult]:
        return []

    async def download(self, result: HunterResult) -> FontPayload:
        return FontPayload(
            font_name="Dummy",
            font_data=b"data",
            file_extension="ttf",
            source="Conforming",
            nameids={},
            metadata={},
        )


class NonConformingHunterMissingMethod:
    def __init__(self):
        self.name: str = "NonConforming"
        self.priority: int = 1
        self.rate_limit: float = 1.5
        self.circuit_breaker_threshold: int = 3
        self.ping_url: str | None = None

    # Missing supports(), search(), and download()


def test_hunter_protocol_conformance():
    hunter = ConformingHunter()
    assert isinstance(hunter, HunterProtocol)


def test_hunter_protocol_non_conformance():
    hunter = NonConformingHunterMissingMethod()
    assert not isinstance(hunter, HunterProtocol)


def test_hunter_protocol_attributes_type():
    hunter = ConformingHunter()
    assert isinstance(hunter.name, str)
    assert isinstance(hunter.priority, int)
    assert isinstance(hunter.rate_limit, float)
    assert isinstance(hunter.circuit_breaker_threshold, int)
    assert hunter.ping_url is None or isinstance(hunter.ping_url, str)


def test_system_font_hunter_conformance():
    hunter = SystemFontHunter()
    assert isinstance(hunter, HunterProtocol)
