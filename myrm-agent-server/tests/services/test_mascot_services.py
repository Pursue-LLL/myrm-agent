"""Unit tests for the Mascot services.

Tests raw agent event to mascot status mapping.
"""

from app.services.mascot import (
    MascotStateMapper,
    MascotStatus,
)


def test_mascot_state_mapper():
    """Verify raw agent framework events map to the correct mascot status states."""
    # Sleeping
    assert MascotStateMapper.map_event_to_mascot_state("agent_idle") == MascotStatus.SLEEPING
    assert MascotStateMapper.map_event_to_mascot_state("session_sleep") == MascotStatus.SLEEPING

    # Thinking
    assert MascotStateMapper.map_event_to_mascot_state("agent_start") == MascotStatus.THINKING
    assert MascotStateMapper.map_event_to_mascot_state("tool_call_start") == MascotStatus.THINKING

    # Panting (Budget Limits)
    assert MascotStateMapper.map_event_to_mascot_state("budget_warning") == MascotStatus.PANTING
    assert MascotStateMapper.map_event_to_mascot_state("token_limit_exceeded") == MascotStatus.PANTING

    # Celebrating
    assert MascotStateMapper.map_event_to_mascot_state("goal_completed") == MascotStatus.CELEBRATING
    assert MascotStateMapper.map_event_to_mascot_state("tests_passed") == MascotStatus.CELEBRATING

    # Dizzy (Errors/Lints)
    assert MascotStateMapper.map_event_to_mascot_state("tool_error", {"error_category": "compile"}) == MascotStatus.DIZZY
