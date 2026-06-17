"""AuthMiddleware integration tests for mobile pair tokens on remote-exposed paths."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.middleware.auth import AuthMiddleware
from app.remote_access.pairing import MOBILE_HUB_LIST_PURPOSE, create_pairing_token


@pytest.fixture(autouse=True)
def _local_remote_webui(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "true")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "true")
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/remote-access/mobile/sessions")
    async def mobile_sessions(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "user_id": getattr(request.state, "user_id", None),
                "trust_zone": getattr(request.state, "trust_zone", None),
            }
        )

    @app.get("/api/v1/agents/chat/{chat_id}/attach")
    async def attach(request: Request, chat_id: str) -> JSONResponse:
        return JSONResponse(
            {
                "user_id": getattr(request.state, "user_id", None),
                "chat_id": chat_id,
            }
        )

    app.add_middleware(AuthMiddleware)
    return app


def test_auth_middleware_accepts_hub_pair_query_on_mobile_sessions() -> None:
    token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    client = TestClient(_build_app())
    response = client.get(
        f"/api/v1/remote-access/mobile/sessions?pair={token}",
        headers={"Host": "abc.trycloudflare.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "local-user"
    assert body["trust_zone"] == "remote_exposed"


def test_auth_middleware_rejects_missing_pair_on_mobile_sessions() -> None:
    client = TestClient(_build_app())
    response = client.get(
        "/api/v1/remote-access/mobile/sessions",
        headers={"Host": "abc.trycloudflare.com"},
    )
    assert response.status_code == 401


def test_auth_middleware_rejects_scoped_pair_on_other_chat_attach() -> None:
    token = create_pairing_token(chat_id="chat-a", purpose="mobile_hub")
    client = TestClient(_build_app())
    response = client.get(
        "/api/v1/agents/chat/chat-b/attach",
        headers={"Host": "abc.trycloudflare.com", "X-Pair-Token": token},
    )
    assert response.status_code == 401


def test_auth_middleware_rejects_hub_list_pair_on_attach() -> None:
    token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    client = TestClient(_build_app())
    response = client.get(
        "/api/v1/agents/chat/chat-a/attach",
        headers={"Host": "abc.trycloudflare.com", "X-Pair-Token": token},
    )
    assert response.status_code == 401


def test_auth_middleware_accepts_scoped_pair_on_matching_chat_attach() -> None:
    token = create_pairing_token(chat_id="chat-a", purpose="mobile_hub")
    client = TestClient(_build_app())
    response = client.get(
        "/api/v1/agents/chat/chat-a/attach",
        headers={"Host": "abc.trycloudflare.com", "X-Pair-Token": token},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "local-user"
