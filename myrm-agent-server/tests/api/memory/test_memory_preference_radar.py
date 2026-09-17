"""Integration and unit tests for memory preference radar service and API endpoints."""

from __future__ import annotations

import pytest

from app.schemas.memory.radar import (
    RadarFeedbackAction,
    RecordImplicitFeedbackRequest,
    UpdatePreferenceRadarRequest,
)
from app.services.memory.preference_radar_service import PreferenceRadarService


@pytest.fixture
def radar_service() -> PreferenceRadarService:
    return PreferenceRadarService()


@pytest.mark.asyncio
async def test_radar_initial_state(radar_service: PreferenceRadarService) -> None:
    session_id = "session-test-01"
    state = await radar_service.get_state(session_id)

    assert state.session_id == session_id
    assert state.recency == 1.0
    assert state.actionability == 1.0
    assert state.technical_depth == 1.0
    assert state.conciseness == 1.0
    assert state.breadth == 1.0
    assert not state.locked
    assert "recency" in state.effective_signal_weights
    assert "importance" in state.effective_signal_weights


@pytest.mark.asyncio
async def test_manual_fine_tuning_and_clamping(radar_service: PreferenceRadarService) -> None:
    session_id = "session-test-02"

    # Test valid boundary tuning
    req = UpdatePreferenceRadarRequest(
        recency=2.2,
        actionability=3.0,  # Max bound
        locked=True,
    )
    state = await radar_service.update_state(session_id, req)

    assert state.recency == 2.2
    assert state.actionability == 3.0
    assert state.locked is True

    from pydantic import ValidationError

    # Ensure out-of-bound is rejected by Pydantic schema validation
    with pytest.raises(ValidationError):
        UpdatePreferenceRadarRequest(actionability=3.5)

    # When locked, implicit feedback should not alter weights
    fb_req = RecordImplicitFeedbackRequest(action=RadarFeedbackAction.MORE_CODE)
    state_after_fb = await radar_service.record_feedback(session_id, fb_req)
    assert state_after_fb.actionability == 3.0


@pytest.mark.asyncio
async def test_implicit_feedback_and_natural_language_heuristic(
    radar_service: PreferenceRadarService,
) -> None:
    session_id = "session-test-03"

    # Natural language asking for code
    req_nl = RecordImplicitFeedbackRequest(
        action=RadarFeedbackAction.POSITIVE_ACCEPT,
        raw_prompt="请直接给出可运行代码，不要啰嗦",
    )
    state = await radar_service.record_feedback(session_id, req_nl)

    # Heuristic should override to MORE_CODE, boosting actionability
    assert state.actionability > 1.0
    assert state.breadth < 1.0


@pytest.mark.asyncio
async def test_reset_to_neutral(radar_service: PreferenceRadarService) -> None:
    session_id = "session-test-04"

    await radar_service.update_state(
        session_id,
        UpdatePreferenceRadarRequest(recency=2.5, conciseness=0.4),
    )

    reset_state = await radar_service.update_state(
        session_id,
        UpdatePreferenceRadarRequest(reset_to_neutral=True),
    )

    assert reset_state.recency == 1.0
    assert reset_state.conciseness == 1.0
