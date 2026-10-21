"""WsAuthMiddleware rejects LAN WebSocket when WebUI session is required."""

from __future__ import annotations

import pytest

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
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


@pytest.mark.asyncio
async def test_ws_middleware_rejects_lan_without_cookie() -> None:
    sent: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    async def receive() -> dict[str, str]:
        return {"type": "websocket.connect"}

    async def downstream(scope, receive, send):  # type: ignore[no-untyped-def]
        raise AssertionError("downstream must not run")

    scope = {
        "type": "websocket",
        "path": "/api/v1/voice/ws",
        "client": ("192.168.1.10", 55555),
        "headers": [],
        "state": {},
    }

    middleware = WsAuthMiddleware(downstream)
    await middleware(scope, receive, send)

    assert sent
    assert sent[0].get("type") == "websocket.http.response.start"
    assert sent[0].get("status") == 403
