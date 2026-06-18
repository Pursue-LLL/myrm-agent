"""Integration: mobile hub pair-token lifecycle through AuthMiddleware + remote-access + attach.

Critical path (pairing, auth middleware, mobile_gate, gateway session tracking, attach gate)
uses real implementations — no mocks.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.general_agent.active_sessions import router as agents_attach_router
from app.api.agents.general_agent.streaming import router as agents_streaming_router
from app.api.remote_access.router import router as remote_access_router
from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.middleware.auth import AuthMiddleware
from app.remote_access.pairing import (
    MOBILE_HUB_CONTROL_PURPOSE,
    MOBILE_HUB_LIST_PURPOSE,
    create_pairing_token,
    parse_pairing_token,
)
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector

_REMOTE_HEADERS = {"Host": "abc.trycloudflare.com"}


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


@pytest.fixture
def integration_client() -> TestClient:
    app = FastAPI()
    app.include_router(remote_access_router, prefix="/api/v1/remote-access")
    app.include_router(agents_attach_router, prefix="/api/v1/agents")
    app.include_router(agents_streaming_router, prefix="/api/v1/agents")
    app.add_middleware(AuthMiddleware)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


async def _wait_for_active_session(chat_id: str, *, attempts: int = 100) -> None:
    gateway = get_agent_gateway()
    for _ in range(attempts):
        sessions = gateway.get_active_sessions()
        if any(str(item.get("chatId")) == chat_id for item in sessions):
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"Gateway did not register active session for {chat_id}")


@pytest.fixture
async def active_chat_with_collector() -> AsyncIterator[str]:
    ACTIVE_COLLECTORS.clear()
    chat_id = "integration-hub-chat"
    gateway = get_agent_gateway()

    async def long_stream() -> AsyncIterator[dict[str, object]]:
        for _ in range(2400):
            await asyncio.sleep(0.05)
            yield {"type": "message", "data": "ping"}

    async def consume_gateway() -> None:
        async for _ in gateway.execute_stream(long_stream(), agent_type="general", session_id=chat_id):
            pass

    gateway_task = asyncio.create_task(consume_gateway())
    collector = StreamContentCollector(chat_id=chat_id, sibling_group_id="integration-sib")
    collector.feed_event({"type": "message", "data": "hello"})

    await _wait_for_active_session(chat_id)

    try:
        yield chat_id
    finally:
        gateway_task.cancel()
        try:
            await gateway_task
        except asyncio.CancelledError:
            pass
        collector.cleanup()
        ACTIVE_COLLECTORS.clear()


class TestMobileHubIntegration:
    @pytest.mark.asyncio
    async def test_hub_list_sessions_upgrade_attach_full_chain(
        self,
        integration_client: TestClient,
        active_chat_with_collector: str,
    ) -> None:
        chat_id = active_chat_with_collector
        list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)

        sessions_response = integration_client.get(
            f"/api/v1/remote-access/mobile/sessions?pair={list_token}",
            headers=_REMOTE_HEADERS,
        )
        assert sessions_response.status_code == 200
        active_sessions = sessions_response.json()["data"]["activeSessions"]
        assert any(str(item.get("chatId")) == chat_id for item in active_sessions)

        upgrade_response = integration_client.post(
            "/api/v1/remote-access/pairing-token",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": list_token},
            json={"chat_id": chat_id, "purpose": MOBILE_HUB_CONTROL_PURPOSE},
        )
        assert upgrade_response.status_code == 200
        scoped_token = upgrade_response.json()["data"]["token"]
        parsed = parse_pairing_token(scoped_token)
        assert parsed is not None
        assert parsed["chat_id"] == chat_id
        assert parsed["purpose"] == MOBILE_HUB_CONTROL_PURPOSE

        attach_response = integration_client.get(
            f"/api/v1/agents/chat/{chat_id}/attach?multiplexed=true",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": scoped_token},
        )
        assert attach_response.status_code == 200
        snapshot = attach_response.json()["data"]["catchup_snapshot"]
        assert isinstance(snapshot, dict)

        refresh_response = integration_client.post(
            "/api/v1/remote-access/pairing-token/refresh",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": scoped_token},
        )
        assert refresh_response.status_code == 200
        refreshed = parse_pairing_token(refresh_response.json()["data"]["token"])
        assert refreshed is not None
        assert refreshed["chat_id"] == chat_id
        assert refreshed["purpose"] == MOBILE_HUB_CONTROL_PURPOSE

    @pytest.mark.asyncio
    async def test_hub_list_upgrade_rejects_inactive_chat(
        self,
        integration_client: TestClient,
        active_chat_with_collector: str,
    ) -> None:
        _ = active_chat_with_collector
        list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
        response = integration_client.post(
            "/api/v1/remote-access/pairing-token",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": list_token},
            json={"chat_id": "chat-not-running", "purpose": MOBILE_HUB_CONTROL_PURPOSE},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_scoped_pair_rejects_attach_on_other_chat(
        self,
        integration_client: TestClient,
        active_chat_with_collector: str,
    ) -> None:
        chat_id = active_chat_with_collector
        scoped_token = create_pairing_token(chat_id=chat_id, purpose=MOBILE_HUB_CONTROL_PURPOSE)
        response = integration_client.get(
            "/api/v1/agents/chat/other-chat/attach?multiplexed=true",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": scoped_token},
        )
        assert response.status_code == 401

    def test_hub_list_pair_rejected_on_attach_without_upgrade(
        self,
        integration_client: TestClient,
    ) -> None:
        list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
        response = integration_client.get(
            "/api/v1/agents/chat/chat-a/attach?multiplexed=true",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": list_token},
        )
        assert response.status_code == 401

    def test_pairing_token_requires_identity_on_testclient_loopback(
        self,
        integration_client: TestClient,
    ) -> None:
        """TestClient client IP is not loopback; remote mode requires session or pair token."""
        response = integration_client.post(
            "/api/v1/remote-access/pairing-token",
            headers={"Host": "127.0.0.1:8080"},
            json={"purpose": MOBILE_HUB_LIST_PURPOSE},
        )
        assert response.status_code == 401

    def test_hub_list_token_refresh(self, integration_client: TestClient) -> None:
        list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
        response = integration_client.post(
            "/api/v1/remote-access/pairing-token/refresh",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": list_token},
        )
        assert response.status_code == 200
        refreshed = parse_pairing_token(response.json()["data"]["token"])
        assert refreshed is not None
        assert refreshed["purpose"] == MOBILE_HUB_LIST_PURPOSE

    @pytest.mark.asyncio
    async def test_scoped_pair_steers_matching_chat_auth_only(
        self,
        integration_client: TestClient,
        active_chat_with_collector: str,
    ) -> None:
        chat_id = active_chat_with_collector
        scoped_token = create_pairing_token(chat_id=chat_id, purpose=MOBILE_HUB_CONTROL_PURPOSE)
        response = integration_client.post(
            f"/api/v1/agents/chats/{chat_id}/steer",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": scoped_token},
            json={"message": "continue"},
        )
        assert response.status_code != 401

    @pytest.mark.asyncio
    async def test_scoped_pair_rejects_steer_on_other_chat(
        self,
        integration_client: TestClient,
        active_chat_with_collector: str,
    ) -> None:
        chat_id = active_chat_with_collector
        scoped_token = create_pairing_token(chat_id=chat_id, purpose=MOBILE_HUB_CONTROL_PURPOSE)
        response = integration_client.post(
            "/api/v1/agents/chats/other-chat/steer",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": scoped_token},
            json={"message": "continue"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_scoped_pair_cancels_matching_chat_auth_only(
        self,
        integration_client: TestClient,
        active_chat_with_collector: str,
    ) -> None:
        chat_id = active_chat_with_collector
        scoped_token = create_pairing_token(chat_id=chat_id, purpose=MOBILE_HUB_CONTROL_PURPOSE)
        with patch(
            "app.services.agent.gateway.get_agent_gateway",
        ) as mock_get_gateway:
            mock_get_gateway.return_value.interrupt_session.return_value = True
            response = integration_client.post(
                f"/api/v1/agents/chats/{chat_id}/cancel",
                headers={**_REMOTE_HEADERS, "X-Pair-Token": scoped_token},
            )
        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_scoped_pair_rejects_cancel_on_other_chat(
        self,
        integration_client: TestClient,
        active_chat_with_collector: str,
    ) -> None:
        chat_id = active_chat_with_collector
        scoped_token = create_pairing_token(chat_id=chat_id, purpose=MOBILE_HUB_CONTROL_PURPOSE)
        response = integration_client.post(
            "/api/v1/agents/chats/other-chat/cancel",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": scoped_token},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_scoped_pair_cancel_interrupts_real_gateway_session(
        self,
        integration_client: TestClient,
        active_chat_with_collector: str,
    ) -> None:
        """Full chain: scoped pair token → chat cancel → real gateway interrupt (no mocks)."""
        chat_id = active_chat_with_collector
        scoped_token = create_pairing_token(chat_id=chat_id, purpose=MOBILE_HUB_CONTROL_PURPOSE)
        gateway = get_agent_gateway()

        cancel_response = integration_client.post(
            f"/api/v1/agents/chats/{chat_id}/cancel",
            headers={**_REMOTE_HEADERS, "X-Pair-Token": scoped_token},
        )
        assert cancel_response.status_code == 200
        body = cancel_response.json()
        assert body["success"] is True
        assert body["data"]["cancelled"] is True
        assert body["data"]["chat_id"] == chat_id

        for _ in range(50):
            sessions = gateway.get_active_sessions()
            if not any(str(item.get("chatId")) == chat_id for item in sessions):
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError(f"Gateway session still active after cancel for {chat_id}")
