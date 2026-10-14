"""Tests for single-tenant auth middleware."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import patch

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
async def test_loopback_local_skips_ingress_db_lookup(auth_app: FastAPI) -> None:
    from unittest.mock import AsyncMock, patch

    with patch("app.middleware.auth.get_public_ingress_base_url", new_callable=AsyncMock) as mock_ingress:
        transport = ASGITransport(app=auth_app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            response = await client.get("/api/v1/protected")
        assert response.status_code == 200
        mock_ingress.assert_not_called()


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


_REMOTE_API_KEY = "test-remote-key"


@pytest.fixture
def remote_auth_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """Auth middleware in remote-exposed mode; callers must reach it from a non-loopback address."""
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
    monkeypatch.setattr(settings_module.settings, "sandbox_api_key", SecretStr(_REMOTE_API_KEY))
    _reset_capabilities_cache_for_testing()

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/api/v1/protected")
    async def protected() -> dict[str, str]:
        return {"ok": "1"}

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/api/v1/health/liveness")
    async def liveness() -> dict[str, str]:
        return {"state": "idle"}

    @app.get("/api/v1/health/doctor")
    async def doctor() -> dict[str, str]:
        return {"overall": "ok"}

    @app.post("/api/v1/health/database/reset")
    async def reset_database() -> dict[str, str]:
        return {"status": "reset"}

    @app.post("/api/v1/a2a/tasks/{task_id}/approve")
    async def approve_task(task_id: str) -> dict[str, str]:
        return {"approved": task_id}

    @app.post("/api/v1/a2a/rpc")
    async def a2a_rpc() -> dict[str, str]:
        return {"jsonrpc": "2.0"}

    yield app
    get_settings.cache_clear()


@asynccontextmanager
async def _remote_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    with (
        patch("app.core.security.auth.identity.is_loopback_ip", return_value=False),
        patch("app.core.security.auth.identity.is_private_network_ip", return_value=False),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://203.0.113.10") as client:
            yield client


@pytest.mark.asyncio
async def test_remote_requires_api_key(remote_auth_app: FastAPI) -> None:
    async with _remote_client(remote_auth_app) as client:
        denied = await client.get("/api/v1/protected")
        allowed = await client.get("/api/v1/protected", headers={"X-Sandbox-Api-Key": _REMOTE_API_KEY})
    assert denied.status_code == 401
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_remote_health_probe_is_public_but_diagnostics_and_operator_actions_are_not(
    remote_auth_app: FastAPI,
) -> None:
    async with _remote_client(remote_auth_app) as client:
        probe = await client.get("/api/v1/health")
        liveness = await client.get("/api/v1/health/liveness")
        doctor_denied = await client.get("/api/v1/health/doctor")
        doctor_allowed = await client.get("/api/v1/health/doctor", headers={"X-Sandbox-Api-Key": _REMOTE_API_KEY})
        reset_denied = await client.post("/api/v1/health/database/reset")
        reset_allowed = await client.post("/api/v1/health/database/reset", headers={"X-Sandbox-Api-Key": _REMOTE_API_KEY})
    assert probe.status_code == 200
    assert liveness.status_code == 200
    assert doctor_denied.status_code == 401
    assert doctor_allowed.status_code == 200
    assert reset_denied.status_code == 401
    assert reset_allowed.status_code == 200


@pytest.mark.asyncio
async def test_remote_a2a_rpc_is_public_but_operator_approval_is_not(remote_auth_app: FastAPI) -> None:
    async with _remote_client(remote_auth_app) as client:
        rpc = await client.post("/api/v1/a2a/rpc")
        approve_denied = await client.post("/api/v1/a2a/tasks/task-1/approve")
        approve_allowed = await client.post("/api/v1/a2a/tasks/task-1/approve", headers={"X-Sandbox-Api-Key": _REMOTE_API_KEY})
    assert rpc.status_code == 200
    assert approve_denied.status_code == 401
    assert approve_allowed.status_code == 200


def test_local_admin_user_id_constant() -> None:
    assert LOCAL_USER_ID == "local-user"
