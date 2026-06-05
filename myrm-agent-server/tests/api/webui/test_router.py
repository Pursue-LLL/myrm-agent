from collections.abc import AsyncGenerator

import httpx
import pytest
from httpx import ASGITransport

from app.main import app


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


async def test_browser_snapshot_no_active_session(client: httpx.AsyncClient) -> None:
    """GET /webui/browser/snapshot returns 404 when no browser session is active."""
    response = await client.get("/webui/browser/snapshot")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "no_active_browser"
