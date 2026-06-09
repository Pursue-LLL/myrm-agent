"""Session invalidation policy for protection toggle vs password disable."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)
from app.services.webui import admin_store
from app.services.webui.auth_service import webui_auth_service
from app.services.webui.passwords import hash_password
from app.services.webui.protection_store import set_password_protection_enabled
from app.services.webui.session import SESSION_COOKIE_NAME, create_session_value, parse_session_value


@pytest.fixture(autouse=True)
def _local_admin(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_disable_protection_keeps_session_cookie_valid() -> None:
    cookie = create_session_value("admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/webui/auth/disable-protection",
            json={"password": "Str0ng!Pass"},
            cookies={SESSION_COOKIE_NAME: cookie},
        )
        assert response.status_code == 200
    assert parse_session_value(cookie) == "admin"


@pytest.mark.asyncio
async def test_enable_protection_invalidates_old_cookie() -> None:
    set_password_protection_enabled(False)
    cookie = create_session_value("admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/webui/auth/protection",
            json={"require_password": True},
        )
        assert response.status_code == 200
    assert parse_session_value(cookie) is None


def test_update_protection_enabled_rotates_only_when_enabling() -> None:
    cookie = create_session_value("admin")
    webui_auth_service.update_protection_enabled(enabled=False)
    assert parse_session_value(cookie) == "admin"
    webui_auth_service.update_protection_enabled(enabled=True)
    assert parse_session_value(cookie) is None
