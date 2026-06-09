"""Tests for the /api/v1/logs/client-error endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="client_logs")
@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_client_error_returns_204(client: AsyncClient):
    resp = await client.post(
        "/api/v1/logs/client-error",
        json={
            "error": "TypeError: Cannot read properties of null",
            "stack": "at Component (/app/page.tsx:12:5)",
            "componentStack": "\n    at Page\n    at Layout",
            "userAgent": "Mozilla/5.0",
            "url": "http://localhost:3000/chat",
            "timestamp": "2026-05-19T10:00:00.000Z",
        },
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_client_error_minimal_payload(client: AsyncClient):
    resp = await client.post(
        "/api/v1/logs/client-error",
        json={"error": "Something went wrong"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_client_error_rejects_oversized_error(client: AsyncClient):
    resp = await client.post(
        "/api/v1/logs/client-error",
        json={"error": "x" * 3000},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_client_error_rejects_empty_body(client: AsyncClient):
    resp = await client.post("/api/v1/logs/client-error", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_client_error_rejects_missing_error_field(client: AsyncClient):
    resp = await client.post(
        "/api/v1/logs/client-error",
        json={"stack": "at foo", "url": "http://localhost"},
    )
    assert resp.status_code == 422
