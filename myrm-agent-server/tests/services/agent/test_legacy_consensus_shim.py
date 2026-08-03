"""Tests for deprecated consensus action_mode → agent + MoA preset shim."""

from __future__ import annotations

from app.services.agent.moa_preset_resolver import MOA_PRESET_DEFAULT_ID, MOA_PRESET_REVIEW_ID
from app.services.agent.params.models import AgentRequest
from app.services.agent.stream_session.orchestrator import _normalize_legacy_consensus_request


def _base_request(**overrides: object) -> AgentRequest:
    payload: dict[str, object] = {
        "query": "hello",
        "message_id": "msg-1",
        "chat_id": "chat-1",
        "action_mode": "agent",
    }
    payload.update(overrides)
    return AgentRequest.model_validate(payload)


def test_consensus_mode_maps_to_agent_with_default_preset() -> None:
    request = _base_request(action_mode="consensus")
    normalized = _normalize_legacy_consensus_request(request)
    assert normalized.action_mode == "agent"
    assert normalized.active_moa_preset_id == MOA_PRESET_DEFAULT_ID


def test_consensus_mode_preserves_explicit_preset() -> None:
    request = _base_request(
        action_mode="consensus",
        active_moa_preset_id=MOA_PRESET_REVIEW_ID,
    )
    normalized = _normalize_legacy_consensus_request(request)
    assert normalized.action_mode == "agent"
    assert normalized.active_moa_preset_id == MOA_PRESET_REVIEW_ID


def test_non_consensus_request_unchanged() -> None:
    request = _base_request(action_mode="agent", active_moa_preset_id=None)
    normalized = _normalize_legacy_consensus_request(request)
    assert normalized.action_mode == "agent"
    assert normalized.active_moa_preset_id is None
