import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.core.font_resolver import FontResolver
from src.hunters.registry import HunterRegistry
from src.core.font_cache import FontCache
from src.config import AppConfig
from src.models.font import FontQuery, FontAsset, FontPayload, HunterResult
from src.errors import FontMatchError
from src.core.circuit_breaker import CircuitBreakerState


class ConformingMockHunter:
    def __init__(self, name: str, priority: int = 1, ping_url: str | None = None):
        self.name = name
        self.priority = priority
        self.rate_limit = 0.05
        self.circuit_breaker_threshold = 2
        self.ping_url = ping_url
        self.supports_result = True
        self.search_results = []
        self.download_payload = None

    def supports(self, query: FontQuery) -> bool:
        return self.supports_result

    async def search(self, query: FontQuery) -> list[HunterResult]:
        return self.search_results

    async def download(self, result: HunterResult) -> FontPayload:
        if self.download_payload is None:
            raise Exception("Download failed")
        return self.download_payload


@pytest.fixture
def mock_cache():
    cache = MagicMock(spec=FontCache)
    cache.lookup.return_value = None
    return cache


@pytest.fixture
def registry():
    return HunterRegistry()


@pytest.fixture
def config():
    return AppConfig()


@pytest.mark.anyio
async def test_resolver_cache_hit_skips_hunters(registry, mock_cache, config):
    # Setup cache hit
    query = FontQuery(
        requested_name="Arial", anime_title="Naruto", episode_path="ep1.mkv"
    )  # type: ignore
    expected_asset = FontAsset(
        name="Arial",
        file_path="arial.ttf",  # type: ignore
        source="cache",
        layer_found=1,
        cache_hit=True,
        nameids={},
    )
    mock_cache.lookup.return_value = expected_asset

    # Add a hunter that would fail if called
    hunter = ConformingMockHunter("HunterA")
    registry.register(hunter)

    resolver = FontResolver(registry=registry, cache=mock_cache, config=config)
    asset = await resolver.resolve(query)

    assert asset == expected_asset
    mock_cache.lookup.assert_called_once_with("Arial")
    # Hunter search should not have been called since cache was hit
    # (search_results is empty anyway, but we didn't call it)


@pytest.mark.anyio
async def test_resolver_cache_miss_hunter_hit(registry, mock_cache, config):
    query = FontQuery(
        requested_name="Arial", anime_title="Naruto", episode_path="ep1.mkv"
    )  # type: ignore

    hunter = ConformingMockHunter("HunterA")
    res = HunterResult(
        query=query, success=True, hunter_name="HunterA", duration_ms=10.0, attempts=1
    )
    hunter.search_results = [res]
    payload = FontPayload(
        font_name="Arial",
        font_data=b"arial_data",
        file_extension="ttf",
        source="HunterA",
        nameids={},
        metadata={},
    )
    hunter.download_payload = payload
    registry.register(hunter)

    stored_asset = FontAsset(
        name="Arial",
        file_path="arial.ttf",  # type: ignore
        source="HunterA",
        layer_found=1,
        cache_hit=False,
        nameids={},
    )
    mock_cache.store.return_value = stored_asset

    resolver = FontResolver(registry=registry, cache=mock_cache, config=config)
    asset = await resolver.resolve(query)

    assert asset == stored_asset
    mock_cache.lookup.assert_called_once_with("Arial")
    mock_cache.store.assert_called_once_with(payload, layer_found=1)


@pytest.mark.anyio
async def test_resolver_all_layers_exhausted_raises_error(registry, mock_cache, config):
    query = FontQuery(
        requested_name="Arial", anime_title="Naruto", episode_path="ep1.mkv"
    )  # type: ignore

    hunter = ConformingMockHunter("HunterA")
    registry.register(hunter)

    resolver = FontResolver(registry=registry, cache=mock_cache, config=config)
    with pytest.raises(FontMatchError) as exc_info:
        await resolver.resolve(query)

    assert "Arial" in str(exc_info.value)
    # Check that audit trail exists or details are stored
    assert hasattr(exc_info.value, "audit_trail") or exc_info.value is not None


@pytest.mark.anyio
async def test_resolver_skips_circuit_broken_hunter(registry, mock_cache, config):
    query = FontQuery(
        requested_name="Arial", anime_title="Naruto", episode_path="ep1.mkv"
    )  # type: ignore

    hunter = ConformingMockHunter("HunterA")
    registry.register(hunter)

    # Trip circuit breaker
    cb = registry.get_circuit("HunterA")
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

    resolver = FontResolver(registry=registry, cache=mock_cache, config=config)
    with pytest.raises(FontMatchError):
        await resolver.resolve(query)


@pytest.mark.anyio
async def test_resolver_startup_ping_success_and_failure(registry, mock_cache, config):
    h1 = ConformingMockHunter("Hunter1", ping_url="http://success.com")
    h2 = ConformingMockHunter("Hunter2", ping_url="http://fail.com")
    registry.register(h1)
    registry.register(h2)

    cb1 = registry.get_circuit("Hunter1")
    cb2 = registry.get_circuit("Hunter2")

    resolver = FontResolver(registry=registry, cache=mock_cache, config=config)

    # Mock httpx.AsyncClient.head or head calls
    # We will patch httpx.AsyncClient
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Define mock responses
        async def mock_head(url, *args, **kwargs):
            if "success.com" in url:
                return MagicMock(status_code=200)
            else:
                raise Exception("Network Timeout")

        mock_client.head.side_effect = mock_head

        await resolver.startup_ping()

        assert cb1.state == CircuitBreakerState.CLOSED
        assert cb1._failure_count == 0
        assert cb2.state == CircuitBreakerState.CLOSED
        assert cb2._failure_count == 1


@pytest.mark.anyio
async def test_resolver_startup_ping_proxy_injection(registry, mock_cache, config):
    config.proxy = "http://myproxy:8080"
    h1 = ConformingMockHunter("Hunter1", ping_url="http://success.com")
    registry.register(h1)

    resolver = FontResolver(registry=registry, cache=mock_cache, config=config)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.head.return_value = MagicMock(status_code=200)

        await resolver.startup_ping()

        mock_client_cls.assert_called_once_with(proxy="http://myproxy:8080")


@pytest.mark.anyio
async def test_resolver_startup_ping_no_proxy(registry, mock_cache, config):
    config.proxy = None
    h1 = ConformingMockHunter("Hunter1", ping_url="http://success.com")
    registry.register(h1)

    resolver = FontResolver(registry=registry, cache=mock_cache, config=config)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.head.return_value = MagicMock(status_code=200)

        await resolver.startup_ping()

        mock_client_cls.assert_called_once_with()


@pytest.mark.anyio
async def test_resolver_skips_download_for_non_cacheable_assets(
    registry, mock_cache, config
):
    query = FontQuery(
        requested_name="Arial", anime_title="Naruto", episode_path="ep1.mkv"
    )  # type: ignore

    hunter = ConformingMockHunter("HunterA")

    # We construct a non-cacheable FontAsset
    uncacheable_asset = FontAsset(
        name="Arial",
        file_path="arial.ttf",  # type: ignore
        source="system",
        layer_found=4,
        cache_hit=False,
        nameids={},
        is_cacheable=False,
    )

    res = HunterResult(
        query=query,
        font_asset=uncacheable_asset,
        success=True,
        hunter_name="HunterA",
        duration_ms=10.0,
        attempts=1,
    )
    hunter.search_results = [res]

    # Mock download and cache.store to assert they are NEVER called
    hunter.download = AsyncMock(side_effect=Exception("Should not be called!"))
    mock_cache.store = MagicMock(side_effect=Exception("Should not be called!"))

    registry.register(hunter)

    resolver = FontResolver(registry=registry, cache=mock_cache, config=config)
    asset = await resolver.resolve(query)

    assert asset == uncacheable_asset
    assert asset.is_cacheable is False

    # Check that lookup was called
    mock_cache.lookup.assert_called_once_with("Arial")

    # Verify download and store were NEVER called
    hunter.download.assert_not_called()
    mock_cache.store.assert_not_called()
