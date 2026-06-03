"""Tests for WebUI admin auth (local / remote)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.main import app
from app.services.webui import admin_store, session
from app.services.webui.passwords import hash_password, verify_password
from app.services.webui.temp_token import temp_token_service


@pytest.fixture(autouse=True)
def _isolate_admin_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "false")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "false")
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def test_password_hash_roundtrip() -> None:
    stored = hash_password("Str0ng!Pass")
    assert verify_password("Str0ng!Pass", stored)
    assert not verify_password("wrong", stored)


def test_temp_token_consume_once() -> None:
    token = temp_token_service.generate_token()
    assert temp_token_service.validate_token(token)
    assert temp_token_service.consume_token(token)
    assert not temp_token_service.consume_token(token)


@pytest.mark.asyncio
async def test_webui_setup_and_login_flow(tmp_path: Path) -> None:
    token = temp_token_service.generate_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        status = await client.get("/webui/auth/status")
        assert status.status_code == 200
        assert status.json()["is_authenticated"] is True

        setup = await client.post(
            "/webui/auth/setup",
            json={"temp_token": token, "username": "admin", "password": "Str0ng!Pass"},
        )
        assert setup.status_code == 200
        assert setup.json()["is_authenticated"] is True
        assert "myrm_webui_session" in setup.cookies

        login = await client.post(
            "/webui/auth/login",
            json={"username": "admin", "password": "Str0ng!Pass"},
            cookies=setup.cookies,
        )
        assert login.status_code == 200
        assert login.json()["is_authenticated"] is True

        bad = await client.post(
            "/webui/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert bad.status_code == 401

    admin_path = tmp_path / "webui" / "admin.json"
    assert admin_path.is_file()
    data = json.loads(admin_path.read_text(encoding="utf-8"))
    assert data["username"] == "admin"


@pytest.mark.asyncio
async def test_webui_remote_requires_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBUI_MODE", "true")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "true")
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        status = await client.get("/webui/auth/status")
        assert status.status_code == 200
        body = status.json()
        assert body["is_setup_done"] is False
        assert body["is_authenticated"] is False


@pytest.mark.asyncio
async def test_token_exchange_requires_admin(tmp_path: Path) -> None:
    token = temp_token_service.generate_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/webui/auth/token-exchange",
            json={"temp_token": token},
        )
        assert response.status_code == 401
