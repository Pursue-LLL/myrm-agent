"""Integration tests for POST /agents/chats/{chat_id}/cancel endpoint."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.utils.runtime.cancellation import CancelReason


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


class TestCancelChatEndpoint:
    def test_cancel_no_active_session_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/agents/chats/nonexistent-chat/cancel")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == 404

    def test_cancel_active_session_success(self, client: TestClient) -> None:
        with patch(
            "app.services.agent.gateway.get_agent_gateway",
        ) as mock_get_gateway:
            gateway = mock_get_gateway.return_value
            gateway.get_active_message_id.return_value = "msg-active"
            gateway.interrupt_session.return_value = True
            with patch(
                "app.api.agents.general_agent.streaming.CancellationRegistry.cancel",
                return_value=True,
            ) as mock_cancel:
                resp = client.post("/api/v1/agents/chats/chat-active/cancel")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["cancelled"] is True
        assert body["data"]["chat_id"] == "chat-active"
        gateway.interrupt_session.assert_called_once_with("chat-active")
        mock_cancel.assert_called_once_with("msg-active", CancelReason.USER_CANCELLED)
