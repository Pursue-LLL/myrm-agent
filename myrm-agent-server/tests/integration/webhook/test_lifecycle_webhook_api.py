"""FastAPI integration tests for lifecycle outbound webhooks endpoints.

[POS] Integration tests covering REST CRUD operations, DB persistence, and /ping endpoint.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.webhook.routes import router as lifecycle_webhook_router


@pytest.fixture
def webhook_app() -> FastAPI:
    """Minimal FastAPI test app mounting lifecycle webhook routes."""
    app = FastAPI()
    app.include_router(lifecycle_webhook_router, prefix="/api")
    return app


@pytest.mark.asyncio
async def test_lifecycle_webhook_crud_and_ping(webhook_app: FastAPI):
    """Verify full CRUD lifecycle and ping probe via FastAPI test client."""
    # Mock socket getaddrinfo to return safe public IP for offline testing
    with patch(
        "socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    ):
        async with AsyncClient(transport=ASGITransport(app=webhook_app), base_url="http://test") as client:
            # 1. List initial webhooks
            res = await client.get("/api/lifecycle-webhooks")
            assert res.status_code == 200
            initial_list = res.json()
            assert isinstance(initial_list, list)

            # 2. Create new webhook endpoint
            create_payload = {
                "name": "Integration Test Hook",
                "url": "https://example.com/api/webhook",
                "secret": "whsec_test_secret_12345",
                "events": ["session_completed", "session_failed"],
                "is_active": True,
                "timeout_seconds": 10,
            }
            create_res = await client.post("/api/lifecycle-webhooks", json=create_payload)
            assert create_res.status_code == 201
            data = create_res.json()
            webhook_id = data["id"]
            assert data["name"] == "Integration Test Hook"
            assert data["is_active"] is True
            assert "session_completed" in data["events"]

            # 3. Update webhook
            update_payload = {"is_active": False, "name": "Updated Hook"}
            update_res = await client.put(f"/api/lifecycle-webhooks/{webhook_id}", json=update_payload)
            assert update_res.status_code == 200
            assert update_res.json()["is_active"] is False
            assert update_res.json()["name"] == "Updated Hook"

            # 4. Delete webhook
            delete_res = await client.delete(f"/api/lifecycle-webhooks/{webhook_id}")
            assert delete_res.status_code == 204

    # 5. Ping endpoint SSRF validation (without mock, testing real 169.254.169.254 block)
    async with AsyncClient(transport=ASGITransport(app=webhook_app), base_url="http://test") as client:
        ping_payload = {
            "url": "http://169.254.169.254/metadata",
            "secret": "whsec_test",
            "timeout_seconds": 5,
        }
        ping_res = await client.post("/api/lifecycle-webhooks/ping", json=ping_payload)
        assert ping_res.status_code == 200
        assert ping_res.json()["success"] is False
        assert "SSRF blocked" in str(ping_res.json()["error"])
