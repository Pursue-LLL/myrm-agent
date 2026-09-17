"""Memory preference pulse radar inspector API endpoints.

[INPUT]
- session_id: str path parameter
- UpdatePreferenceRadarRequest, RecordImplicitFeedbackRequest
- preference_radar_service

[OUTPUT]
- PreferenceRadarStateResponse

[POS]
REST API endpoints powering the dynamic preference radar inspector drawer and manual fine-tuning.
"""

from __future__ import annotations

from fastapi import APIRouter, Path

from app.schemas.memory.radar import (
    PreferenceRadarStateResponse,
    RecordImplicitFeedbackRequest,
    UpdatePreferenceRadarRequest,
)
from app.services.memory.preference_radar_service import preference_radar_service

router = APIRouter(prefix="/radar", tags=["memory-radar"])


@router.get("/{session_id}", response_model=PreferenceRadarStateResponse)
async def get_session_radar(
    session_id: str = Path(..., description="Chat session or conversation ID"),
) -> PreferenceRadarStateResponse:
    """Retrieve current 5-dimensional preference radar state for a session."""
    return await preference_radar_service.get_state(session_id)


@router.post("/{session_id}/tune", response_model=PreferenceRadarStateResponse)
async def tune_session_radar(
    req: UpdatePreferenceRadarRequest,
    session_id: str = Path(..., description="Chat session or conversation ID"),
) -> PreferenceRadarStateResponse:
    """Manually fine-tune preference dimensions, lock state, or reset to baseline."""
    return await preference_radar_service.update_state(session_id, req)


@router.post("/{session_id}/feedback", response_model=PreferenceRadarStateResponse)
async def submit_radar_feedback(
    req: RecordImplicitFeedbackRequest,
    session_id: str = Path(..., description="Chat session or conversation ID"),
) -> PreferenceRadarStateResponse:
    """Submit an implicit feedback event (e.g. more code, be concise) to fit preferences."""
    return await preference_radar_service.record_feedback(session_id, req)
