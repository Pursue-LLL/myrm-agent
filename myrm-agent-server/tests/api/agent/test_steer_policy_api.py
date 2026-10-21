"""Integration tests for policy-mode steer and steer-metrics endpoints."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.services.agent.steering import SteeringRegistry, reset_for_tests


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Ensure clean registry and policy queues for each test."""
    reset_for_tests()
    with SteeringRegistry._lock:
        SteeringRegistry._tokens.clear()


class TestSteerPolicyEndpoint:
    def test_policy_mode_injects_with_metrics(self, client: TestClient) -> None:
        SteeringRegistry.register("chat-pol-api", SteeringToken())
        resp = client.post(
            "/api/v1/agents/chats/chat-pol-api/steer",
            json={"message": "pivot now", "mode": "policy", "quotedRef": "msg-7"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["mode"] == "policy"
        assert body["data"]["deduped"] is False
        assert body["data"]["metrics"]["injected"] == 1

    def test_policy_mode_no_active_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/agents/chats/ghost-chat/steer",
            json={"message": "hello", "mode": "policy"},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == 404

    def test_direct_mode_unchanged(self, client: TestClient) -> None:
        SteeringRegistry.register("chat-direct", SteeringToken())
        resp = client.post(
            "/api/v1/agents/chats/chat-direct/steer",
            json={"message": "go left"},
        )
        body = resp.json()
        assert body["success"] is True
        assert "mode" not in body["data"]

    def test_policy_mode_case_insensitive(self, client: TestClient) -> None:
        SteeringRegistry.register("chat-case", SteeringToken())
        resp = client.post(
            "/api/v1/agents/chats/chat-case/steer",
            json={"message": "pivot", "mode": "Policy"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["mode"] == "policy"

    def test_steer_metrics_endpoint(self, client: TestClient) -> None:
        SteeringRegistry.register("chat-met", SteeringToken())
        client.post(
            "/api/v1/agents/chats/chat-met/steer",
            json={"message": "hint", "mode": "policy"},
        )
        resp = client.get("/api/v1/agents/chats/chat-met/steer-metrics")
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["metrics"]["received"] == 1

    def test_steer_metrics_no_active_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/agents/chats/ghost-chat/steer-metrics")
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == 404
