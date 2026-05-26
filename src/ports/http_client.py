from typing import Protocol, runtime_checkable
import httpx


@runtime_checkable
class HttpClientPort(Protocol):
    def create_client(self, timeout_s: float | None = None) -> httpx.AsyncClient:
        """Create a pre-configured httpx.AsyncClient instance.

        Args:
            timeout_s: Optional timeout in seconds to override the default.

        Returns:
            A pre-configured httpx.AsyncClient.
        """
        ...
