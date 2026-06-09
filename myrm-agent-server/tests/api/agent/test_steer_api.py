"""Integration tests for POST /agents/chats/{chat_id}/steer endpoint."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.services.agent.steering_registry import SteeringRegistry


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Ensure a clean SteeringRegistry for each test."""
    with SteeringRegistry._lock:
        SteeringRegistry._tokens.clear()


class TestSteerEndpoint:
    def test_steer_no_active_session_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/agents/chats/nonexistent-chat/steer",
            json={"message": "hello"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == 404

    def test_steer_empty_message_returns_400(self, client: TestClient) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-400", token)
        resp = client.post(
            "/api/v1/agents/chats/chat-400/steer",
            json={"message": "   "},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == 400

    def test_steer_success_with_active_session(self, client: TestClient) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-ok", token)

        resp = client.post(
            "/api/v1/agents/chats/chat-ok/steer",
            json={"message": "focus on performance"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["steered"] is True
        assert body["data"]["chat_id"] == "chat-ok"
        assert token.has_pending

    def test_steer_message_reaches_token(self, client: TestClient) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-msg", token)

        client.post(
            "/api/v1/agents/chats/chat-msg/steer",
            json={"message": "use bullet points"},
        )
        msgs = token.activate()
        assert msgs == ["use bullet points"]

    def test_steer_multiple_messages_queue(self, client: TestClient) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-multi", token)

        client.post(
            "/api/v1/agents/chats/chat-multi/steer",
            json={"message": "first hint"},
        )
        client.post(
            "/api/v1/agents/chats/chat-multi/steer",
            json={"message": "second hint"},
        )
        msgs = token.activate()
        assert msgs == ["first hint", "second hint"]

    def test_steer_after_unregister_returns_404(self, client: TestClient) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-unreg", token)
        SteeringRegistry.unregister("chat-unreg")

        resp = client.post(
            "/api/v1/agents/chats/chat-unreg/steer",
            json={"message": "too late"},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == 404

    def test_steer_camel_case_body(self, client: TestClient) -> None:
        """Ensure camelCase body works (Pydantic alias_generator)."""
        token = SteeringToken()
        SteeringRegistry.register("chat-camel", token)

        resp = client.post(
            "/api/v1/agents/chats/chat-camel/steer",
            json={"message": "camelCase test"},
        )
        body = resp.json()
        assert body["success"] is True

    def test_steer_xss_payload_passthrough(self, client: TestClient) -> None:
        """XSS-like content passes through (sanitization is rendering-level)."""
        token = SteeringToken()
        SteeringRegistry.register("chat-xss", token)
        xss = "<img src=x onerror=alert(1)>"
        resp = client.post(
            "/api/v1/agents/chats/chat-xss/steer",
            json={"message": xss},
        )
        assert resp.json()["success"] is True
        msgs = token.activate()
        assert msgs == [xss]

    def test_steer_unicode_chinese(self, client: TestClient) -> None:
        """Unicode (Chinese + emoji) messages handled correctly."""
        token = SteeringToken()
        SteeringRegistry.register("chat-zh", token)
        msg = "请专注于性能优化 🚀 不要使用外部依赖"
        resp = client.post(
            "/api/v1/agents/chats/chat-zh/steer",
            json={"message": msg},
        )
        assert resp.json()["success"] is True
        msgs = token.activate()
        assert msgs == [msg]

    def test_steer_long_message_100kb(self, client: TestClient) -> None:
        """100KB message accepted by API endpoint."""
        token = SteeringToken()
        SteeringRegistry.register("chat-bigmsg", token)
        big = "X" * 100_000
        resp = client.post(
            "/api/v1/agents/chats/chat-bigmsg/steer",
            json={"message": big},
        )
        assert resp.json()["success"] is True
        msgs = token.activate()
        assert len(msgs[0]) == 100_000

    def test_steer_rapid_fire(self, client: TestClient) -> None:
        """Multiple steer requests in quick succession all get queued."""
        token = SteeringToken()
        SteeringRegistry.register("chat-rapid", token)
        for i in range(10):
            resp = client.post(
                "/api/v1/agents/chats/chat-rapid/steer",
                json={"message": f"hint-{i}"},
            )
            assert resp.json()["success"] is True
        msgs = token.activate()
        assert len(msgs) == 10
        assert msgs == [f"hint-{i}" for i in range(10)]

    def test_steer_newlines_preserved(self, client: TestClient) -> None:
        """Newlines in message are preserved (not stripped)."""
        token = SteeringToken()
        SteeringRegistry.register("chat-nl", token)
        msg = "line1\nline2\n\nline4"
        resp = client.post(
            "/api/v1/agents/chats/chat-nl/steer",
            json={"message": msg},
        )
        assert resp.json()["success"] is True
        msgs = token.activate()
        assert msgs == [msg]

    def test_steer_missing_body_field(self, client: TestClient) -> None:
        """Missing 'message' field returns 422 validation error."""
        token = SteeringToken()
        SteeringRegistry.register("chat-no-field", token)
        resp = client.post(
            "/api/v1/agents/chats/chat-no-field/steer",
            json={"wrong_field": "hello"},
        )
        assert resp.status_code == 422

    def test_steer_invalid_json(self, client: TestClient) -> None:
        """Invalid JSON body returns 422."""
        resp = client.post(
            "/api/v1/agents/chats/any-chat/steer",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
