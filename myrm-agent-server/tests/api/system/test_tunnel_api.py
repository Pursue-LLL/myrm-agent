from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system.router import router
from app.core.infra.tunnel.manager import TunnelError, TunnelStatus


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")
    return TestClient(app)


def test_local_network_returns_lan_url(client: TestClient) -> None:
    with patch("app.api.system.router.get_local_ip", return_value="192.168.1.42"):
        response = client.get("/api/v1/system/local-network?port=3000")

    assert response.status_code == 200
    body = response.json()
    assert body["ip"] == "192.168.1.42"
    assert body["url"] == "http://192.168.1.42:3000"


def test_tunnel_start_rejects_without_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/system/tunnel/start",
        json={"port": 3000, "password_protection_enabled": False},
    )

    assert response.status_code == 400
    assert "Password protection" in response.json()["detail"]


def test_tunnel_status_when_idle(client: TestClient) -> None:
    with patch("app.api.system.router.get_tunnel_manager") as mock_manager_factory:
        mock_manager = mock_manager_factory.return_value
        mock_manager.get_status = AsyncMock(return_value=TunnelStatus(
            running=False,
            url=None,
            target_port=None,
            ingress_synced=False,
        ))

        response = client.get("/api/v1/system/tunnel/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["running"] is False
    assert payload["url"] is None


def test_tunnel_start_success(client: TestClient) -> None:
    with patch("app.api.system.router.get_tunnel_manager") as mock_manager_factory:
        mock_manager = mock_manager_factory.return_value
        mock_manager.start = AsyncMock(
            return_value=TunnelStatus(
                running=True,
                url="https://abc.trycloudflare.com",
                target_port=3000,
                ingress_synced=True,
            ),
        )

        response = client.post(
            "/api/v1/system/tunnel/start",
            json={"port": 3000, "password_protection_enabled": True},
        )

    assert response.status_code == 200
    assert response.json()["url"] == "https://abc.trycloudflare.com"


def test_tunnel_start_maps_tunnel_error(client: TestClient) -> None:
    with patch("app.api.system.router.get_tunnel_manager") as mock_manager_factory:
        mock_manager = mock_manager_factory.return_value
        mock_manager.start = AsyncMock(side_effect=TunnelError("cloudflared missing"))

        response = client.post(
            "/api/v1/system/tunnel/start",
            json={"port": 3000, "password_protection_enabled": True},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "cloudflared missing"
