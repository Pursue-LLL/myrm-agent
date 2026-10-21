"""Unit tests for PhaseTransitionTracker."""

from __future__ import annotations

from app.services.agent.stream_session.phase_stepper import PhaseTransitionTracker


def test_initial_planning_phase_emission() -> None:
    tracker = PhaseTransitionTracker(message_id="msg-101")
    event = tracker.emit_initial_if_needed()
    assert event is not None
    assert event["type"] == "phase_transition"
    assert event["messageId"] == "msg-101"
    data = event["data"]
    assert isinstance(data, dict)
    assert data["phase"] == "planning"
    assert data["phase_index"] == 1
    assert data["active_lane"] == "agent"
    assert data["node_id"] == 1

    # Second call should be None (idempotent)
    assert tracker.emit_initial_if_needed() is None


def test_tool_start_transitions_to_execution_lane() -> None:
    tracker = PhaseTransitionTracker(message_id="msg-102")
    tracker.emit_initial_if_needed()

    # 1. MCP tool
    mcp_event = tracker.on_chunk({"type": "tool_start", "name": "mcp__stripe__charge"})
    assert mcp_event is not None
    data = mcp_event["data"]
    assert isinstance(data, dict)
    assert data["phase"] == "executing"
    assert data["phase_index"] == 2
    assert data["active_lane"] == "mcp"
    assert data["node_id"] == 15

    # 2. Sandbox bash tool
    bash_event = tracker.on_chunk({"type": "tool_start", "name": "bash"})
    assert bash_event is not None
    b_data = bash_event["data"]
    assert isinstance(b_data, dict)
    assert b_data["active_lane"] == "sandbox"
    assert b_data["node_id"] == 17

    # 3. User HITL question tool
    user_event = tracker.on_chunk({"type": "tool_start", "name": "ask_question"})
    assert user_event is not None
    u_data = user_event["data"]
    assert isinstance(u_data, dict)
    assert u_data["active_lane"] == "user"
    assert u_data["node_id"] == 14


def test_reasoning_switches_to_llm_lane() -> None:
    tracker = PhaseTransitionTracker(message_id="msg-103")
    tracker.emit_initial_if_needed()

    event = tracker.on_chunk({"type": "reasoning", "data": "Thinking step..."})
    assert event is not None
    data = event["data"]
    assert isinstance(data, dict)
    assert data["active_lane"] == "llm"


def test_verification_and_completion_transitions() -> None:
    tracker = PhaseTransitionTracker(message_id="msg-104")
    tracker.emit_initial_if_needed()

    # Verification verdict
    verify_event = tracker.on_chunk({"type": "verification_verdict", "data": {"passed": True}})
    assert verify_event is not None
    v_data = verify_event["data"]
    assert isinstance(v_data, dict)
    assert v_data["phase"] == "verifying"
    assert v_data["phase_index"] == 3
    assert v_data["node_id"] == 26

    # Message end completion
    complete_event = tracker.on_chunk({"type": "message_end"})
    assert complete_event is not None
    c_data = complete_event["data"]
    assert isinstance(c_data, dict)
    assert c_data["phase"] == "completed"
    assert c_data["node_id"] == 30
