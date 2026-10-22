"""A steer or redirect into a running turn passes the same risk gate as a chat message."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.services.agent.steering import SteeringRegistry
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

_DETECTION = "app.services.risk.detection.get_detection_service"


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def running_turn() -> Iterator[SteeringToken]:
    token = SteeringToken()
    with SteeringRegistry._lock:
        SteeringRegistry._tokens.clear()
    SteeringRegistry.register("chat-risk", token)
    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        yield token
    with SteeringRegistry._lock:
        SteeringRegistry._tokens.clear()


@pytest.mark.parametrize("kind", ["steer", "redirect"])
def test_secret_is_refused_and_never_reaches_the_turn(client: TestClient, running_turn: SteeringToken, kind: str) -> None:
    resp = client.post(f"/api/v1/agents/chats/chat-risk/{kind}", json={"message": f"use {SECRET} instead"})

    body = resp.json()
    assert body["success"] is False
    assert body["code"] == 403
    assert not running_turn.has_pending


@pytest.mark.parametrize("kind", ["steer", "redirect"])
def test_clean_text_still_reaches_the_turn(client: TestClient, running_turn: SteeringToken, kind: str) -> None:
    resp = client.post(f"/api/v1/agents/chats/chat-risk/{kind}", json={"message": "only keep the 2026 rows"})

    assert resp.json()["success"] is True
    assert running_turn.has_pending


def test_secret_in_a_reply_to_an_agent_question_is_refused(client: TestClient, running_turn: SteeringToken) -> None:
    """The reply form (``in_reply_to_call_id``) is the same typed text; the agent's own question is not screened."""
    resp = client.post(
        "/api/v1/agents/chats/chat-risk/steer",
        json={"message": f"it is {SECRET}", "inReplyToCallId": "call-1", "questionContext": "Which key should I use?"},
    )

    assert resp.json()["success"] is False
    assert not running_turn.has_pending
