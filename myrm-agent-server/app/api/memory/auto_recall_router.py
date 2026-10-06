"""
[POS] app/api/memory/auto_recall_router.py
[INPUT] app/schemas/auto_recall.py, app/services/memory/auto_recall_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.auto_recall import (
    AutoRecallDecisionResponse,
    AutoRecallEvaluateRequest,
    SessionClearResponse,
    SlidingWindowStatsResponse,
)
from app.services.memory.auto_recall_service import (
    AutoRecallService,
    get_auto_recall_service,
)

router = APIRouter(prefix="/auto-recall", tags=["auto_recall"])


@router.post(
    "/evaluate",
    response_model=AutoRecallDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate lifecycle context and execute targeted experience auto-recall",
)
def evaluate_auto_recall(
    request: AutoRecallEvaluateRequest,
    service: AutoRecallService = Depends(get_auto_recall_service),
) -> AutoRecallDecisionResponse:
    """Filter triggers, apply 5-turn sliding deduplication, and fail-open rerank candidates."""
    return service.evaluate_and_recall(request)


@router.get(
    "/stats/{session_id}",
    response_model=SlidingWindowStatsResponse,
    summary="Get multi-turn sliding window suppression stats for a session",
)
def get_sliding_window_stats(
    session_id: str,
    service: AutoRecallService = Depends(get_auto_recall_service),
) -> SlidingWindowStatsResponse:
    """Retrieve active turn count and suppressed candidate count for the session."""
    return service.get_sliding_window_stats(session_id)


@router.delete(
    "/sessions/{session_id}",
    response_model=SessionClearResponse,
    summary="Purge sliding window state upon session completion",
)
def clear_session_state(
    session_id: str,
    service: AutoRecallService = Depends(get_auto_recall_service),
) -> SessionClearResponse:
    """Clear memory deduplication history for the specified session."""
    return service.clear_session(session_id)
