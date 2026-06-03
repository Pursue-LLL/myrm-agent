"""Session rotation and cookie invalidation for WebUI auth."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.main import app
from app.services.webui import admin_store
from app.services.webui.passwords import hash_password
from app.services.webui.session import SESSION_COOKIE_NAME, create_session_value, parse_session_value
from app.services.webui.session import rotate_session_signing_key


@pytest.fixture(autouse=True)
def _local_admin(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "false")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "false")
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()
    admin_store.save_admin("admin", hash_password("Str0ng!Pass"))
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def test_rotate_session_signing_key_invalidates_cookie() -> None:
    old_value = create_session_value("admin")
    assert parse_session_value(old_value) == "admin"
    rotate_session_signing_key()
    assert parse_session_value(old_value) is None
    assert parse_session_value(create_session_value("admin")) == "admin"


@pytest.mark.asyncio
async def test_change_password_issues_new_session_cookie() -> None:
    old_cookie = create_session_value("admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/webui/auth/change-password",
            json={"current_password": "Str0ng!Pass", "new_password": "Str0ng!Pass2"},
            cookies={SESSION_COOKIE_NAME: old_cookie},
        )
        assert response.status_code == 200
        assert parse_session_value(old_cookie) is None
        new_cookie = response.cookies.get(SESSION_COOKIE_NAME)
        assert new_cookie is not None
        assert parse_session_value(new_cookie) == "admin"

        login_old = await client.post(
            "/webui/auth/login",
            json={"username": "admin", "password": "Str0ng!Pass"},
        )
        assert login_old.status_code == 401

        login_new = await client.post(
            "/webui/auth/login",
            json={"username": "admin", "password": "Str0ng!Pass2"},
        )
        assert login_new.status_code == 200
