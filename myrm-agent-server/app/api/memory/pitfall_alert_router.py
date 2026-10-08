"""FastAPI router for proactive pitfall alert and decision assist engine.

[POS]
Exposes REST endpoints for query evaluation, postmortem seeding,
session topic muting, and operational telemetry.

[INPUT]
- fastapi (APIRouter, Depends, status)
- app.schemas.pitfall_alert (EvaluateInputRequest, MuteSubjectRequest,
  PitfallAlertStatusResponse, PitfallEvaluationResponse, SeedTriadRequest, UnmuteSubjectRequest)
- app.services.memory.pitfall_alert.provider (PitfallAlertServiceProvider, get_pitfall_alert_service)

[OUTPUT]
- router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.pitfall_alert import (
    EvaluateInputRequest,
    MuteSubjectRequest,
    PitfallAlertStatusResponse,
    PitfallEvaluationResponse,
    SeedTriadRequest,
    UnmuteSubjectRequest,
)
from app.services.memory.pitfall_alert.provider import (
    PitfallAlertServiceProvider,
    get_pitfall_alert_service,
)

router = APIRouter(prefix="/pitfall-alert", tags=["memory-pitfall-alert"])


@router.post(
    "/evaluate",
    response_model=PitfallEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate input query for decision intent and match past pitfalls",
)
async def evaluate_query(
    request: EvaluateInputRequest,
    service: PitfallAlertServiceProvider = Depends(get_pitfall_alert_service),
) -> PitfallEvaluationResponse:
    """Scan query for architectural commitment intent and proactively alert on matching failure postmortems."""
    return await service.evaluate_query(request)


@router.post(
    "/seed",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new historical postmortem causal triad",
)
async def seed_triad(
    request: SeedTriadRequest,
    service: PitfallAlertServiceProvider = Depends(get_pitfall_alert_service),
) -> dict[str, str]:
    """Seed historical failure lesson into the retrieval ledger."""
    service.register_triad(request)
    return {"status": "success", "subject": request.subject}


@router.post(
    "/mute",
    status_code=status.HTTP_200_OK,
    summary="Mute alerts for a specific technical topic in the session",
)
async def mute_subject(
    request: MuteSubjectRequest,
    service: PitfallAlertServiceProvider = Depends(get_pitfall_alert_service),
) -> dict[str, str]:
    """Suppress subsequent alerts for the specified topic within this session."""
    service.mute_subject(session_id=request.session_id, subject=request.subject)
    return {"status": "muted", "session_id": request.session_id, "subject": request.subject}


@router.post(
    "/unmute",
    status_code=status.HTTP_200_OK,
    summary="Unmute alerts for a specific technical topic in the session",
)
async def unmute_subject(
    request: UnmuteSubjectRequest,
    service: PitfallAlertServiceProvider = Depends(get_pitfall_alert_service),
) -> dict[str, str]:
    """Restore alerts for the specified topic within this session."""
    service.unmute_subject(session_id=request.session_id, subject=request.subject)
    return {"status": "unmuted", "session_id": request.session_id, "subject": request.subject}


@router.get(
    "/status",
    response_model=PitfallAlertStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get pitfall alert engine status and metrics",
)
async def get_status(
    service: PitfallAlertServiceProvider = Depends(get_pitfall_alert_service),
) -> PitfallAlertStatusResponse:
    """Report engine operational counters and active states."""
    return service.get_status()
