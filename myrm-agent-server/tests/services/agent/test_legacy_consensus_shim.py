"""Tests for removed consensus action_mode rejection."""

from __future__ import annotations

from app.services.agent.params.models import AgentRequest
from app.services.agent.stream_session.orchestrator import _reject_legacy_consensus_request


def _base_request(**overrides: object) -> AgentRequest:
    payload: dict[str, object] = {
        "query": "hello",
        "message_id": "msg-1",
        "chat_id": "chat-1",
        "action_mode": "agent",
    }
    payload.update(overrides)
    return AgentRequest.model_validate(payload)


def test_consensus_mode_returns_400_response() -> None:
    request = _base_request(action_mode="consensus")
    response = _reject_legacy_consensus_request(request)
    assert response is not None
    assert response.status_code == 400


def test_non_consensus_request_passes() -> None:
    request = _base_request(action_mode="agent", active_moa_preset_id=None)
    assert _reject_legacy_consensus_request(request) is None
