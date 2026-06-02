"""Integration tests for Quick Tunnel API (no manager mocks)."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)


def test_tunnel_start_stop_roundtrip_when_cloudflared_missing(client: TestClient) -> None:
    with patch(
        "app.core.infra.tunnel.manager.TunnelManager._ensure_quick_tunnel_allowed",
    ):
        start = client.post(
            "/api/v1/system/tunnel/start",
            json={"port": 3000, "password_protection_enabled": True},
        )
        assert start.status_code == 400
        assert "cloudflared" in start.json()["detail"].lower()

        stop = client.post("/api/v1/system/tunnel/stop")
        assert stop.status_code == 200
        assert stop.json()["running"] is False


def test_tunnel_status_after_failed_start(client: TestClient) -> None:
    with patch(
        "app.core.infra.tunnel.manager.TunnelManager._ensure_quick_tunnel_allowed",
    ):
        client.post(
            "/api/v1/system/tunnel/start",
            json={"port": 3000, "password_protection_enabled": True},
        )
        status = client.get("/api/v1/system/tunnel/status")
        assert status.status_code == 200
        assert status.json()["running"] is False
