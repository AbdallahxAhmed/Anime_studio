import asyncio
from pathlib import Path
import structlog
import httpx
from typing import TYPE_CHECKING
from src.core.font_cache import FontCache
from src.config import AppConfig
from src.models.font import FontQuery, FontAsset
from src.errors import FontMatchError, PipelineStoppedError
from src.ports.font_hunter import HunterProtocol

if TYPE_CHECKING:
    from src.hunters.registry import HunterRegistry

logger = structlog.get_logger()


def _raise_if_stopped(stop_event: asyncio.Event | None) -> None:
    """Keep cooperative cancellation neutral throughout font resolution."""
    if stop_event is not None and stop_event.is_set():
        raise PipelineStoppedError("Font resolution stopped by user")


class FontResolver:
    """Orchestrator for the 6-layer font resolution chain with circuit breakers and rate limits."""

    def __init__(
        self,
        registry: "HunterRegistry",
        cache: FontCache,
        config: AppConfig,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        self.registry = registry
        self.cache = cache
        self.config = config
        self._stop_event = stop_event

    def for_run(
        self,
        discovery_root: Path | None,
        stop_event: asyncio.Event | None = None,
    ) -> "FontResolver":
        """Return a resolver whose scoped hunters cannot affect another run."""
        return FontResolver(
            registry=self.registry.for_run(discovery_root, stop_event),
            cache=self.cache,
            config=self.config,
            stop_event=stop_event,
        )

    async def resolve(self, query: FontQuery) -> FontAsset:
        """Resolve a font query via the persistent cache or active hunters fallback."""
        _raise_if_stopped(self._stop_event)
        logger.info("Starting font resolution", font_name=query.requested_name)
        audit_trail = []

        # Layer 1: Cache Lookup
        cached_asset = self.cache.lookup(query.requested_name)
        _raise_if_stopped(self._stop_event)
        if cached_asset is not None:
            logger.info("Font resolved from cache", font_name=query.requested_name)
            return cached_asset

        audit_trail.append("Cache miss.")

        # Fallback to Hunters
        for hunter in self.registry.iter_hunters():
            _raise_if_stopped(self._stop_event)
            if not hunter.supports(query):
                audit_trail.append(f"Hunter {hunter.name} does not support query.")
                logger.debug("Hunter does not support query", hunter_name=hunter.name)
                continue

            cb = self.registry.get_circuit(hunter.name)
            try:
                # Apply rate limiting throttle
                if hunter.rate_limit > 0:
                    logger.debug(
                        "Applying rate limit delay",
                        hunter_name=hunter.name,
                        delay=hunter.rate_limit,
                    )
                    await asyncio.sleep(hunter.rate_limit)
                    _raise_if_stopped(self._stop_event)

                logger.info("Attempting resolution via hunter", hunter_name=hunter.name)
                results = await hunter.search(query)
                _raise_if_stopped(self._stop_event)
                if not results:
                    audit_trail.append(
                        f"Hunter {hunter.name} returned 0 search results."
                    )
                    continue

                # System fonts resolve in-place — skip download and cache
                if results[0].font_asset and not results[0].font_asset.is_cacheable:
                    cb.record_success()
                    logger.info(
                        "Font successfully resolved in-place",
                        font_name=query.requested_name,
                        source=hunter.name,
                    )
                    return results[0].font_asset

                # Download first result
                payload = await hunter.download(results[0])
                _raise_if_stopped(self._stop_event)

                # Cache and return asset
                asset = self.cache.store(payload, layer_found=hunter.priority)
                _raise_if_stopped(self._stop_event)
                cb.record_success()
                logger.info(
                    "Font successfully resolved and cached",
                    font_name=query.requested_name,
                    source=hunter.name,
                )
                return asset
            except asyncio.CancelledError:
                raise
            except PipelineStoppedError:
                raise
            except Exception as e:
                audit_trail.append(f"Hunter {hunter.name} failed: {e}")
                logger.warning(
                    "Hunter failed during resolution",
                    hunter_name=hunter.name,
                    error=str(e),
                )
                cb.record_failure()

        # All layers exhausted
        error_msg = f"Font '{query.requested_name}' not found on any known source. Mux will proceed without this font."
        logger.error(
            "font_not_found_anywhere",
            font_name=query.requested_name,
            layers_tried=audit_trail,
            detail="Font could not be located on any known source. Mux will proceed without this font attachment.",
        )
        err = FontMatchError(error_msg)
        err.audit_trail = audit_trail  # type: ignore[attr-defined]  # dynamic property on custom exception subclass
        raise err

    async def _ping_hunter(
        self, hunter: HunterProtocol, client: httpx.AsyncClient
    ) -> None:
        """Ping an individual hunter and update its circuit breaker."""
        if not hunter.ping_url:
            return

        cb = self.registry.get_circuit(hunter.name)
        try:
            async with asyncio.timeout(self.config.startup_ping_timeout_s):
                resp = await client.head(hunter.ping_url)
                if resp.status_code >= 400:
                    raise Exception(f"HTTP status code {resp.status_code}")
                cb.record_success()
                logger.debug(
                    "Hunter ping succeeded",
                    hunter_name=hunter.name,
                    url=hunter.ping_url,
                )
        except Exception as e:
            logger.warning(
                "Startup ping failed. Hunter will still be attempted during resolution.",
                hunter_name=hunter.name,
                url=hunter.ping_url,
                error=str(e),
            )
            # Record a single failure on startup ping failure (don't force trip)
            cb.record_failure()

    async def startup_ping(self) -> None:
        """Concurrent health ping for all network hunters using TaskGroup."""
        logger.info("Initializing concurrent startup pings for network hunters")
        proxy = self.config.proxy if self.config.proxy else None
        client = httpx.AsyncClient(proxy=proxy) if proxy else httpx.AsyncClient()
        async with client as client:
            try:
                async with asyncio.TaskGroup() as tg:
                    # Registry iter_hunters sorts them, but we want to ping all hunters in _hunters
                    for hunter in self.registry._hunters.values():
                        if hunter.ping_url:
                            tg.create_task(self._ping_hunter(hunter, client))
            except* Exception:
                # ExceptionGroup raised by TaskGroup. Sub-tasks handled their exceptions.
                pass
        logger.info("Startup pings completed")
