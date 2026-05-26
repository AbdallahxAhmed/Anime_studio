import ast
from pathlib import Path
import httpx
import pytest
from src.errors import ConfigurationError
from src.adapters.http_client import HttpClientAdapter, RetryAsyncTransport


def test_http_client_adapter_creation():
    adapter = HttpClientAdapter(
        proxy_url="http://127.0.0.1:1080", default_timeout_s=5.0
    )
    assert adapter.proxy_url == "http://127.0.0.1:1080"
    assert adapter.default_timeout_s == 5.0

    client = adapter.create_client()
    assert isinstance(client, httpx.AsyncClient)
    assert client.timeout.read == 5.0


def test_http_client_adapter_no_proxy():
    adapter = HttpClientAdapter(proxy_url=None)
    assert adapter.proxy_url is None

    client = adapter.create_client()
    assert isinstance(client, httpx.AsyncClient)


def test_http_client_adapter_malformed_proxy():
    with pytest.raises(ConfigurationError):
        HttpClientAdapter(proxy_url="not_a_valid_url")

    with pytest.raises(ConfigurationError):
        HttpClientAdapter(proxy_url="http://")

    with pytest.raises(ConfigurationError):
        HttpClientAdapter(proxy_url="ftp://127.0.0.1")


def test_proxy_validation_schemes():
    for scheme in ["http", "https", "socks5", "socks4", "socks5h"]:
        adapter = HttpClientAdapter(proxy_url=f"{scheme}://127.0.0.1:1080")
        assert adapter.proxy_url == f"{scheme}://127.0.0.1:1080"


@pytest.mark.anyio
async def test_retry_async_transport_5xx(mocker):
    transport = RetryAsyncTransport(max_retries=2, backoff_factor=0.001)

    mock_response_500 = mocker.Mock(spec=httpx.Response)
    mock_response_500.status_code = 500
    mock_response_500.aclose = mocker.AsyncMock()

    mock_response_200 = mocker.Mock(spec=httpx.Response)
    mock_response_200.status_code = 200

    mock_super_handle = mocker.patch(
        "httpx.AsyncHTTPTransport.handle_async_request",
        side_effect=[mock_response_500, mock_response_500, mock_response_200],
    )

    request = httpx.Request("GET", "http://example.com")
    resp = await transport.handle_async_request(request)

    assert resp.status_code == 200
    assert mock_super_handle.call_count == 3


@pytest.mark.anyio
async def test_retry_async_transport_conn_error(mocker):
    transport = RetryAsyncTransport(max_retries=2, backoff_factor=0.001)

    mock_response_200 = mocker.Mock(spec=httpx.Response)
    mock_response_200.status_code = 200

    mock_super_handle = mocker.patch(
        "httpx.AsyncHTTPTransport.handle_async_request",
        side_effect=[httpx.ConnectError("connection failed"), mock_response_200],
    )

    request = httpx.Request("GET", "http://example.com")
    resp = await transport.handle_async_request(request)

    assert resp.status_code == 200
    assert mock_super_handle.call_count == 2


def test_http_client_adapter_imports_isolation():
    adapter_file = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "adapters"
        / "http_client.py"
    )

    with open(adapter_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                assert root_name in [
                    "typing",
                    "asyncio",
                    "httpx",
                    "src",
                    "urllib",
                ] or is_stdlib(root_name), f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_name = node.module.split(".")[0]
                assert root_name in [
                    "typing",
                    "asyncio",
                    "httpx",
                    "src",
                    "urllib",
                ] or is_stdlib(root_name), f"Forbidden import from: {node.module}"


def is_stdlib(module_name: str) -> bool:
    import sys

    if module_name in sys.builtin_module_names:
        return True
    try:
        mod = __import__(module_name)
        file = getattr(mod, "__file__", None)
        if file is None:
            return True
        return "stdlib" in file or "lib" in file.lower() or "python" in file.lower()
    except Exception:
        return False
