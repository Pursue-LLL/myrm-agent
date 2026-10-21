"""Tests for steering policy mode — dedup, envelope, metrics (additive)."""

import pytest
from myrm_agent_harness.agent.orchestration.steering import MAX_NOTE_CHARS
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.services.agent.steering import (
    SteeringRegistry,
    policy_metrics,
    policy_steer,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Ensure clean registry and policy queues for each test."""
    reset_for_tests()
    with SteeringRegistry._lock:
        SteeringRegistry._tokens.clear()


def _register(chat_id: str) -> SteeringToken:
    token = SteeringToken()
    SteeringRegistry.register(chat_id, token)
    return token


class TestPolicySteer:
    def test_policy_injects_through_live_token(self) -> None:
        token = _register("chat-pol-1")
        outcome = policy_steer("chat-pol-1", "pivot to file X", quoted_ref="msg-1")
        assert outcome["status"] == "injected"
        assert outcome["injected"] == 1
        assert outcome["deduped"] is False
        assert token.has_pending

    def test_policy_no_active_returns_no_active(self) -> None:
        outcome = policy_steer("ghost-chat", "hello")
        assert outcome["status"] == "no_active"

    def test_policy_too_large_rejected(self) -> None:
        _register("chat-pol-2")
        outcome = policy_steer("chat-pol-2", "x" * (MAX_NOTE_CHARS + 1))
        assert outcome["status"] == "too_large"

    def test_policy_sequential_repeats_each_inject_once(self) -> None:
        # Consumed notes are not carriers for future turns: each call injects.
        # Same-window double-submit dedup is covered in harness queue tests.
        _register("chat-pol-3")
        first = policy_steer("chat-pol-3", "same hint")
        second = policy_steer("chat-pol-3", "same hint")
        assert first["status"] == "injected"
        assert second["status"] == "injected"
        assert second["deduped"] is False

    def test_policy_envelope_labels_side_channel(self) -> None:
        token = _register("chat-pol-4")
        policy_steer("chat-pol-4", "skip the tests")
        msgs = token.collect_all_steering_messages()
        assert len(msgs) == 1
        assert "queued during active run" in msgs[0]
        assert "does not authorize" in msgs[0]

    def test_policy_metrics_counter(self) -> None:
        _register("chat-pol-5")
        assert policy_metrics("chat-pol-5")["received"] == 0
        policy_steer("chat-pol-5", "hint a")
        metrics = policy_metrics("chat-pol-5")
        assert metrics["received"] == 1
        assert metrics["injected"] == 1

    def test_policy_metrics_unknown_chat_zeros(self) -> None:
        assert policy_metrics("never-seen") == {
            "received": 0,
            "dedup_dropped": 0,
            "evicted": 0,
            "injected": 0,
        }
