from collections.abc import AsyncGenerator

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


async def test_get_qrcode_image_endpoint_with_url(client: httpx.AsyncClient) -> None:
    response = await client.get("/webui/qrcode.png?url=https://test.trycloudflare.com")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == "inline; filename=webui-qrcode.png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


async def test_get_qrcode_image_endpoint_with_host_port(client: httpx.AsyncClient) -> None:
    response = await client.get("/webui/qrcode.png?host=192.168.1.100&port=3000")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


async def test_welcome_page_shows_the_requested_address(client: httpx.AsyncClient) -> None:
    response = await client.get("/webui/welcome?host=192.168.1.100&port=3000")
    assert response.status_code == 200
    assert "http://192.168.1.100:3000" in response.text


@pytest.mark.parametrize("host", ["192.168.1.100", "my-host.local", "[::1]", "fe80::1"])
async def test_welcome_page_accepts_hostnames_and_ip_literals(client: httpx.AsyncClient, host: str) -> None:
    response = await client.get("/webui/welcome", params={"host": host, "port": 3000})
    assert response.status_code == 200
    assert host in response.text


@pytest.mark.parametrize("path", ["/webui/welcome", "/webui/qrcode.png"])
@pytest.mark.parametrize("host", ['"><script>alert(1)</script>', "x' onerror='1", "a b", "a/b", "h&port=1", "<b>"])
async def test_host_parameter_rejects_anything_that_is_not_a_hostname(client: httpx.AsyncClient, path: str, host: str) -> None:
    """The welcome page is served without login and writes ``host`` into HTML and script, so only host characters pass."""
    response = await client.get(path, params={"host": host})
    assert response.status_code == 422


async def test_browser_snapshot_requires_chat_id(client: httpx.AsyncClient) -> None:
    """GET /webui/browser/snapshot returns 400 when chat_id is missing."""
    response = await client.get("/webui/browser/snapshot")
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "missing_chat_id"


async def test_browser_snapshot_no_active_session(client: httpx.AsyncClient) -> None:
    """GET /webui/browser/snapshot returns 404 when no browser session is active."""
    response = await client.get("/webui/browser/snapshot?chat_id=chat-missing")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "no_active_browser"
