"""Tests for ConsolidationService steering decision recording into working memory."""

import pytest
from myrm_agent_harness.api import LocalWorkingMemoryBlock

from app.services.memory.consolidation_service import ConsolidationService


@pytest.fixture(autouse=True)
def _cleanup_consolidation() -> None:
    """Ensure clean active session state for each test."""
    ConsolidationService._active_sessions_state.clear()
    LocalWorkingMemoryBlock.reset()


def test_record_steering_decision_basic() -> None:
    session_id = "test-session-steer-1"
    ConsolidationService.record_steering_decision(
        session_id=session_id,
        reply="Adopt Blue-Green deployment",
        call_id="call_123456",
    )

    state = ConsolidationService.get_live_working_state(session_id=session_id)
    scratchpad = state.get("scratchpad")
    assert isinstance(scratchpad, dict)
    assert scratchpad.get("decision_123456") == "Adopt Blue-Green deployment"


def test_record_steering_decision_with_context() -> None:
    session_id = "test-session-steer-2"
    question = "Which deployment strategy should we adopt for staging?"
    reply = "Proceed with Canary 10% rollout"

    ConsolidationService.record_steering_decision(
        session_id=session_id,
        reply=reply,
        question_context=question,
        call_id="call_abcdef",
    )

    state = ConsolidationService.get_live_working_state(session_id=session_id)
    scratchpad = state.get("scratchpad")
    assert isinstance(scratchpad, dict)
    val = scratchpad.get("decision_abcdef")
    assert val is not None
    assert "Which deployment strategy" in str(val)
    assert "Canary 10%" in str(val)


def test_record_steering_decision_syncs_to_active_local_block() -> None:
    LocalWorkingMemoryBlock.initialize(goal="Deploy service")

    ConsolidationService.record_steering_decision(
        session_id="test-session-steer-3",
        reply="Use Redis caching",
        call_id="call_999888",
    )

    local_memo = LocalWorkingMemoryBlock.get_scratchpad("steer_999888")
    assert local_memo == "Use Redis caching"
