"""Session invalidation policy for protection toggle vs password disable."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)
from app.services.webui import admin_store
from app.services.webui.auth_service import webui_auth_service
from app.services.webui.passwords import hash_password
from app.services.webui.protection_store import is_password_protection_enabled, set_password_protection_enabled
from app.services.webui.session import SESSION_COOKIE_NAME, create_session_value, parse_session_value


@pytest.fixture(autouse=True)
def _local_admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
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


@pytest.mark.asyncio
async def test_protection_toggle_rejects_unauthenticated_remote_client() -> None:
    transport = ASGITransport(app=app, client=("203.0.113.10", 50000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put("/webui/auth/protection", json={"require_password": False})
    assert response.status_code == 401
    assert is_password_protection_enabled()


@pytest.mark.asyncio
async def test_protection_toggle_accepts_remote_client_with_session() -> None:
    transport = ASGITransport(app=app, client=("203.0.113.10", 50000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/webui/auth/protection",
            json={"require_password": False},
            cookies={SESSION_COOKIE_NAME: create_session_value("admin")},
        )
    assert response.status_code == 200
    assert not is_password_protection_enabled()


def test_update_protection_enabled_rotates_only_when_enabling() -> None:
    cookie = create_session_value("admin")
    webui_auth_service.update_protection_enabled(enabled=False)
    assert parse_session_value(cookie) == "admin"
    webui_auth_service.update_protection_enabled(enabled=True)
    assert parse_session_value(cookie) is None
