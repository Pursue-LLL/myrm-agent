"""HTTP/WebSocket integration tests for extension router endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.extension import router as extension_router
from app.api.extension import ws_router as extension_ws_router
from app.services.extension.bridge import get_extension_bridge


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(extension_router, prefix="/api/v1")
    app.include_router(extension_ws_router, prefix="/api/v1/ws")
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_extension_bridge() -> None:
    bridge = get_extension_bridge()
    bridge._connected = False
    bridge._ws = None
    bridge._extension_version = ""
    bridge._browser_name = ""
    bridge._authorized_domains = []
    bridge._tabs = []


def test_extension_status_includes_token_required_false_by_default(client: TestClient) -> None:
    with patch("app.api.extension.router.settings") as mock_settings:
        mock_settings.extension_auth_token = SecretStr("")

        response = client.get("/api/v1/extension/status")

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["token_required"] is False


def test_extension_status_token_required_when_configured(client: TestClient) -> None:
    with patch("app.api.extension.router.settings") as mock_settings:
        mock_settings.extension_auth_token = SecretStr("secret-token")

        response = client.get("/api/v1/extension/status")

    assert response.status_code == 200
    assert response.json()["token_required"] is True


def test_extension_ws_rejects_invalid_token(client: TestClient) -> None:
    with patch("app.api.extension.router.settings") as mock_settings:
        mock_settings.extension_auth_token = SecretStr("expected")

        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws/extension?token=wrong"):
                pass


def test_extension_ws_accepts_valid_token_and_hello(client: TestClient) -> None:
    with patch("app.api.extension.router.settings") as mock_settings:
        mock_settings.extension_auth_token = SecretStr("expected")

        with client.websocket_connect("/api/v1/ws/extension?token=expected") as ws:
            ws.send_text(json.dumps({"type": "hello", "version": "1.0.0", "browser": "Chrome"}))

            status_response = client.get("/api/v1/extension/status")
            assert status_response.status_code == 200
            body = status_response.json()
            assert body["connected"] is True
            assert body["extension_version"] == "1.0.0"
            assert body["browser_name"] == "Chrome"

            ws.close()
