import asyncio
from urllib.parse import urlparse
import httpx

from src.errors import ConfigurationError
from src.ports.http_client import HttpClientPort


from typing import Any


class RetryAsyncTransport(httpx.AsyncHTTPTransport):
    def __init__(
        self, max_retries: int = 3, backoff_factor: float = 0.1, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        retries = 0
        while True:
            try:
                response = await super().handle_async_request(request)
                if response.status_code >= 500 and retries < self.max_retries:
                    retries += 1
                    await response.aclose()
                    await asyncio.sleep(self.backoff_factor * (2 ** (retries - 1)))
                    continue
                return response
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                if retries < self.max_retries:
                    retries += 1
                    await asyncio.sleep(self.backoff_factor * (2 ** (retries - 1)))
                    continue
                raise e


def validate_proxy(proxy_url: str) -> None:
    if not proxy_url:
        return
    try:
        parsed = urlparse(proxy_url)
        if not parsed.scheme or parsed.scheme not in [
            "http",
            "https",
            "socks5",
            "socks4",
            "socks5h",
        ]:
            raise ConfigurationError(
                f"Malformed or unsupported proxy scheme: {proxy_url}"
            )
        if not parsed.netloc:
            raise ConfigurationError(f"Malformed proxy URL (missing host): {proxy_url}")
    except Exception as e:
        if isinstance(e, ConfigurationError):
            raise e
        raise ConfigurationError(f"Malformed proxy URL: {proxy_url}") from e


class HttpClientAdapter(HttpClientPort):
    def __init__(
        self, proxy_url: str | None = None, default_timeout_s: float = 120.0
    ) -> None:
        self.proxy_url = proxy_url.strip() if proxy_url else None
        if self.proxy_url:
            validate_proxy(self.proxy_url)
        self.default_timeout_s = default_timeout_s

    def create_client(self, timeout_s: float | None = None) -> httpx.AsyncClient:
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

        # Configure the retry transport
        if self.proxy_url:
            transport = RetryAsyncTransport(
                proxy=self.proxy_url,
                limits=limits,
            )
        else:
            transport = RetryAsyncTransport(
                limits=limits,
            )

        timeout = timeout_s if timeout_s is not None else self.default_timeout_s
        return httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
        )
