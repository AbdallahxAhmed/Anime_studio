from typing import Protocol, runtime_checkable
from src.models.font import FontQuery, FontPayload, HunterResult


@runtime_checkable
class HunterProtocol(Protocol):
    """Protocol defining the contract for font acquisition sources (hunters)."""

    name: str
    priority: int
    rate_limit: float
    circuit_breaker_threshold: int
    ping_url: str | None

    def supports(self, query: FontQuery) -> bool:
        """Check if this hunter supports the given font query."""
        ...

    async def search(self, query: FontQuery) -> list[HunterResult]:
        """Search the hunter's source for a font matching the query."""
        ...

    async def download(self, result: HunterResult) -> FontPayload:
        """Download raw font data for the given search result."""
        ...
