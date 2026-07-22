from asyncio import Event
from dataclasses import dataclass, field
from os.path import normcase
from pathlib import Path
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


@dataclass(frozen=True)
class FontSearchScope:
    """Immutable, normalized discovery boundary for one font-resolution run."""

    discovery_root: Path | None
    identity: str = field(init=False)

    def __post_init__(self) -> None:
        if self.discovery_root is None:
            object.__setattr__(self, "identity", "<unscoped>")
            return

        resolved_root = Path(self.discovery_root).expanduser().resolve()
        object.__setattr__(self, "discovery_root", resolved_root)
        object.__setattr__(self, "identity", normcase(str(resolved_root)))


@runtime_checkable
class RunScopedHunterProtocol(Protocol):
    """Optional factory contract for hunters whose discovery is run-scoped."""

    def for_run(
        self,
        discovery_root: Path | None,
        stop_event: Event | None = None,
    ) -> HunterProtocol:
        """Return a fresh hunter bounded to one discovery root."""
        ...
