"""Tests for WebSocket auth middleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient

from app.core.security.auth.identity import resolve_identity_from_ws_scope
from app.middleware.ws_auth import WsAuthMiddleware


def test_resolve_identity_from_ws_scope_reads_api_key_header() -> None:
    scope = {
        "type": "websocket",
        "path": "/api/voice/ws",
        "headers": [(b"x-sandbox-api-key", b"secret-key")],
        "client": ("127.0.0.1", 12345),
    }
    identity = resolve_identity_from_ws_scope(scope)
    assert identity.client_ip == "127.0.0.1"


@pytest.fixture
def ws_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    monkeypatch.setenv("SANDBOX_API_KEY", "ws-test-key")
    from app.config.settings import get_settings
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    get_settings.cache_clear()
    _reset_capabilities_cache_for_testing()

    app = FastAPI()
    app.add_middleware(WsAuthMiddleware)

    @app.websocket("/api/voice/ws")
    async def voice_ws(ws: WebSocket) -> None:
        await ws.accept()
        user_id = getattr(ws.state, "user_id", "")
        await ws.send_text(user_id or "missing")
        await ws.close()

    return app


def test_ws_loopback_with_api_key_sets_user_id(ws_app: FastAPI) -> None:
    client = TestClient(ws_app)
    with client.websocket_connect(
        "/api/voice/ws",
        headers={"X-Sandbox-Api-Key": "ws-test-key"},
    ) as ws:
        assert ws.receive_text() == "sandbox"
