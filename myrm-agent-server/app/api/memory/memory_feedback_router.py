"""FastAPI router for natural language memory feedback and live correction endpoints.

[INPUT]
- app.schemas.memory_feedback
- app.services.memory.memory_feedback_service

[OUTPUT]
- router: APIRouter with live correction and feedback routes

[POS]
app.api.memory.memory_feedback_router
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.memory_feedback import (
    CorrectionDetectRequest,
    CorrectionDetectResponse,
    LiveCorrectionExecuteRequest,
    LiveCorrectionExecuteResponse,
)
from app.services.memory.memory_feedback_service import memory_feedback_service

router = APIRouter(prefix="/feedback", tags=["Memory Feedback & Live Correction"])


@router.post(
    "/detect",
    response_model=CorrectionDetectResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect live correction intent from natural language utterance",
)
async def detect_correction_endpoint(
    payload: CorrectionDetectRequest,
) -> CorrectionDetectResponse:
    """Detect whether user utterance contains correction signal and extract slots."""
    return memory_feedback_service.detect_intent(payload.utterance)


@router.post(
    "/live-correction",
    response_model=LiveCorrectionExecuteResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute live memory correction and return user acknowledgement receipt",
)
async def execute_live_correction_endpoint(
    payload: LiveCorrectionExecuteRequest,
) -> LiveCorrectionExecuteResponse:
    """Execute live memory mutation and generate user-facing acknowledgement text."""
    return memory_feedback_service.execute_live_correction(
        utterance=payload.utterance,
        candidates=payload.candidates,
    )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check for live correction subsystem",
)
async def feedback_subsystem_health() -> dict[str, str]:
    """Return health status of the memory feedback subsystem."""
    return {"status": "ok", "subsystem": "memory_live_correction"}
