"""WebSocket must respect WebUI session gate when local API protection is enabled."""

from __future__ import annotations

import pytest

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.core.security.auth.identity import resolve_identity_from_ws_scope
from app.middleware.ws_auth import WsAuthMiddleware
from app.services.webui import admin_store
from app.services.webui.passwords import hash_password
from app.services.webui.protection_store import set_password_protection_enabled


@pytest.fixture(autouse=True)
def _protected_remote(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "true")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "true")
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()
    admin_store.save_admin("admin", hash_password("Str0ng!Pass"))
    set_password_protection_enabled(True)
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def test_ws_identity_denied_without_cookie_on_lan() -> None:
    scope = {
        "type": "websocket",
        "path": "/api/v1/voice/ws",
        "client": ("192.168.1.88", 54321),
        "headers": [],
    }
    identity = resolve_identity_from_ws_scope(scope)
    assert identity.user_id is None
    assert identity.loopback is False


def test_ws_middleware_rejects_unauthenticated_lan_upgrade() -> None:
    from app.services.webui.access_policy import local_api_requires_session

    assert local_api_requires_session() is True


@pytest.mark.asyncio
async def test_ws_middleware_rejects_unauthenticated_lan_upgrade_403() -> None:
    scope = {
        "type": "websocket",
        "path": "/api/v1/voice/ws",
        "client": ("192.168.1.88", 54321),
        "headers": [],
        "state": {},
    }

    async def mock_app(scope: dict, receive: object, send: object) -> None:
        return None

    middleware = WsAuthMiddleware(app=mock_app)

    sent_messages = []

    async def mock_send(msg: dict) -> None:
        sent_messages.append(msg)

    async def mock_receive() -> dict:
        return {}

    await middleware(scope, mock_receive, mock_send)

    assert len(sent_messages) == 2
    assert sent_messages[0]["type"] == "websocket.http.response.start"
    assert sent_messages[0]["status"] == 403
    assert sent_messages[1]["type"] == "websocket.http.response.body"
    assert sent_messages[1]["body"] == b"Unauthorized"
