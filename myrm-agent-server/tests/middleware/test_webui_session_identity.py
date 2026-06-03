"""WebUI session cookie must authorize local API when protection is enabled."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.core.security.auth.identity import resolve_identity_from_http_scope
from app.middleware.auth import AuthMiddleware
from app.services.webui import admin_store
from app.services.webui.passwords import hash_password
from app.services.webui.protection_store import set_password_protection_enabled
from app.services.webui.session import SESSION_COOKIE_NAME, create_session_value


@pytest.fixture(autouse=True)
def _local_protected_admin(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/protected/ping")
    async def ping(request: Request) -> JSONResponse:
        user_id = getattr(request.state, "user_id", None)
        return JSONResponse({"user_id": user_id})

    app.add_middleware(AuthMiddleware)
    return app


def test_resolve_identity_denied_without_session_on_lan() -> None:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/agents",
        "client": ("192.168.1.50", 12345),
        "headers": [],
    }
    identity = resolve_identity_from_http_scope(scope)
    assert identity.user_id is None


def test_resolve_identity_webui_session_unit() -> None:
    session_value = create_session_value("admin")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/agents",
        "client": ("192.168.1.20", 12345),
        "headers": [
            (b"cookie", f"{SESSION_COOKIE_NAME}={session_value}".encode()),
        ],
    }
    identity = resolve_identity_from_http_scope(scope)
    assert identity.user_id == "local-user"
    assert identity.auth_source == "webui_session"
