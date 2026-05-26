# Port Contracts: Font System

**Feature**: 003-font-system | **Date**: 2026-05-26

## HunterProtocol

**Module**: `src/ports/font_hunter.py`
**Type**: `typing.Protocol` with `@runtime_checkable`

```python
from typing import Protocol, runtime_checkable
from src.models.font import FontQuery, FontPayload, HunterResult

@runtime_checkable
class HunterProtocol(Protocol):
    """Contract for font acquisition sources.

    Implementations are discovered at runtime via the HunterRegistry.
    Each hunter represents one font resolution strategy (local scan,
    network API, MKV extraction, etc.).
    """

    @property
    def name(self) -> str:
        """Unique identifier for this hunter."""
        ...

    @property
    def priority(self) -> int:
        """Resolution order. Lower = tried first. Maps to layer number."""
        ...

    @property
    def rate_limit(self) -> float:
        """Maximum requests per second to this source."""
        ...

    @property
    def circuit_breaker_threshold(self) -> int:
        """Consecutive failures before circuit opens. Default: 3."""
        ...

    @property
    def ping_url(self) -> str | None:
        """URL for startup health check. None for local-only hunters."""
        ...

    def supports(self, query: FontQuery) -> bool:
        """Pre-filter: can this hunter handle the given query?

        Synchronous — no I/O. Used to skip irrelevant hunters early.
        """
        ...

    async def search(self, query: FontQuery) -> list[HunterResult]:
        """Search for fonts matching the query.

        Returns list of matches (may be empty). Raises HunterError
        on source-level failures (network, auth, rate limit).
        """
        ...

    async def download(self, result: HunterResult) -> FontPayload:
        """Download a matched font.

        Returns FontPayload with raw bytes and metadata.
        Raises HunterError on download failure.
        """
        ...
```

### Contract Rules

1. `name` MUST be unique across all registered hunters.
2. `priority` MUST map to the 6-layer scheme (1=Cache, 2=MKV, 3=Sibling, 4=System, 5=Network, 6=Fuzzy).
3. `rate_limit` MUST be > 0. For local hunters, use a high value (e.g., `1000.0`).
4. `circuit_breaker_threshold` MUST be >= 1. Default 3.
5. `ping_url` MUST be `None` for local-only hunters (Layers 1-4). Network hunters (Layer 5) MUST provide a URL.
6. `supports()` MUST NOT perform I/O. It is a synchronous capability check.
7. `search()` MUST return an empty list on no-match, not raise.
8. `search()` MUST raise `HunterError` on source failures (timeout, auth, etc.).
9. `download()` MUST raise `HunterError` on download failure.
10. All methods MUST be safe to call concurrently from `asyncio`.

### Runtime Validation

```python
# Registration-time check
assert isinstance(hunter, HunterProtocol), f"{hunter} does not implement HunterProtocol"
```

### Static Validation

```bash
mypy --strict src/ports/font_hunter.py  # Must produce zero errors
```

## FontResolverPort (internal — no separate port file)

The 6-layer resolution orchestrator (`src/core/font_resolver.py`) is a concrete class, not a protocol. Per §XII (YAGNI), there is exactly one implementation. If future need arises (e.g., mock resolver for TUI testing), a protocol can be extracted then.
