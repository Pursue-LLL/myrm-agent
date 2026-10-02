"""Hub list token upgrades to scoped control tokens."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.remote_access.router import router as remote_access_router
from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.middleware.auth import AuthMiddleware
from app.remote_access.pairing import (
    BROWSER_TAKEOVER_PURPOSE,
    MOBILE_HUB_CONTROL_PURPOSE,
    MOBILE_HUB_LIST_PURPOSE,
    create_pairing_token,
    parse_pairing_token,
)


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
    app.include_router(remote_access_router, prefix="/api/v1/remote-access")
    app.add_middleware(AuthMiddleware)
    return app


def test_hub_list_pair_mints_scoped_control_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.services.chat.chat_service import ChatService

    list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    # Only chat existence matters now (running or finished alike).
    monkeypatch.setattr(ChatService, "get_chat_metadata", AsyncMock(return_value=MagicMock()))

    client = TestClient(_build_app())
    response = client.post(
        "/api/v1/remote-access/pairing-token",
        headers={"Host": "abc.trycloudflare.com", "X-Pair-Token": list_token},
        json={"chat_id": "chat-42", "purpose": "mobile_hub"},
    )
    assert response.status_code == 200
    body = response.json()
    scoped_token = body["data"]["token"]
    assert body["data"]["mobilePath"] == f"/mobile/status/chat-42?pair={scoped_token}"
    parsed = parse_pairing_token(scoped_token)
    assert parsed is not None
    assert parsed["chat_id"] == "chat-42"
    assert parsed["purpose"] == MOBILE_HUB_CONTROL_PURPOSE


def test_hub_list_pair_rejects_missing_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    from app.services.chat.chat_service import ChatService

    list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    # Missing (or trashed — excluded by the repo) chats never mint tokens.
    monkeypatch.setattr(ChatService, "get_chat_metadata", AsyncMock(return_value=None))

    client = TestClient(_build_app())
    response = client.post(
        "/api/v1/remote-access/pairing-token",
        headers={"Host": "abc.trycloudflare.com", "X-Pair-Token": list_token},
        json={"chat_id": "chat-stale", "purpose": "mobile_hub"},
    )
    assert response.status_code == 404


def test_issue_browser_takeover_pairing_token_from_scoped_control_pair() -> None:
    control_token = create_pairing_token(
        chat_id="chat-42",
        purpose=MOBILE_HUB_CONTROL_PURPOSE,
    )
    client = TestClient(_build_app())
    response = client.post(
        "/api/v1/remote-access/pairing-token",
        headers={"Host": "abc.trycloudflare.com", "X-Pair-Token": control_token},
        json={"chat_id": "chat-42", "purpose": "browser_takeover"},
    )
    assert response.status_code == 200
    body = response.json()
    takeover_token = body["data"]["token"]
    assert body["data"]["mobilePath"] == f"/mobile/takeover/chat-42?pair={takeover_token}"
    parsed = parse_pairing_token(takeover_token)
    assert parsed is not None
    assert parsed["chat_id"] == "chat-42"
    assert parsed["purpose"] == BROWSER_TAKEOVER_PURPOSE


def test_refresh_browser_takeover_pairing_token_keeps_takeover_mobile_path() -> None:
    token = create_pairing_token(chat_id="chat-42", purpose=BROWSER_TAKEOVER_PURPOSE)
    client = TestClient(_build_app())
    response = client.post(
        "/api/v1/remote-access/pairing-token/refresh",
        headers={"Host": "abc.trycloudflare.com", "X-Pair-Token": token},
    )
    assert response.status_code == 200
    body = response.json()
    refreshed = body["data"]["token"]
    assert body["data"]["mobilePath"] == f"/mobile/takeover/chat-42?pair={refreshed}"
