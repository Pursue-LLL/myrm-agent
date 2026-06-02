"""Tests for single-tenant auth middleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.auth import LOCAL_USER_ID, AuthMiddleware


@pytest.fixture
def auth_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/v1/protected")
    async def protected() -> dict[str, str]:
        return {"ok": "1"}

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    return app


@pytest.mark.asyncio
async def test_loopback_allowed_local(auth_app: FastAPI) -> None:
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/api/v1/protected")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_public_health_skips_auth(auth_app: FastAPI) -> None:
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_remote_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from pydantic import SecretStr

    import app.config.settings as settings_module
    from app.config.deploy_mode import get_deploy_mode
    from app.config.settings import get_settings
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "true")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "true")
    get_deploy_mode.cache_clear()
    get_settings.cache_clear()
    monkeypatch.setattr(
        settings_module.settings,
        "sandbox_api_key",
        SecretStr("test-remote-key"),
    )
    _reset_capabilities_cache_for_testing()

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/v1/protected")
    async def protected() -> dict[str, str]:
        return {"ok": "1"}

    transport = ASGITransport(app=app)
    with (
        patch("app.core.security.auth.identity.is_loopback_ip", return_value=False),
        patch("app.core.security.auth.identity.is_private_network_ip", return_value=False),
    ):
        async with AsyncClient(transport=transport, base_url="http://203.0.113.10") as client:
            denied = await client.get("/api/v1/protected")
            allowed = await client.get(
                "/api/v1/protected",
                headers={"X-Sandbox-Api-Key": "test-remote-key"},
            )
    assert denied.status_code == 401
    assert allowed.status_code == 200
    get_settings.cache_clear()


def test_local_admin_user_id_constant() -> None:
    assert LOCAL_USER_ID == "local-user"
