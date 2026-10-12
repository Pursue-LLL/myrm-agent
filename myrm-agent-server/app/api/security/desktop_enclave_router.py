"""API endpoints for Computer-Use Safe Enclave, panic control, and live intent HUD.

[INPUT]
- EvaluateActionRequest, ChallengeDecisionRequest, PanicTriggerRequest
- Query parameters: limit

[OUTPUT]
- EvaluateActionResponse, ChallengeDecisionResponse, PanicStatusResponse
- list[ActionEnclaveChallengeDto], LiveIntentFeedResponse

[POS]
Server API layer. Exposes REST interfaces for safe computer-use execution.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.desktop_enclave import (
    ActionEnclaveChallengeDto,
    ChallengeDecisionRequest,
    ChallengeDecisionResponse,
    EvaluateActionRequest,
    EvaluateActionResponse,
    LiveIntentFeedResponse,
    PanicStatusResponse,
    PanicTriggerRequest,
)
from app.services.security.desktop_enclave_service import default_desktop_enclave_service

router = APIRouter(prefix="/desktop-enclave", tags=["desktop-enclave"])


@router.post("/evaluate", response_model=EvaluateActionResponse)
async def evaluate_desktop_action(
    request: EvaluateActionRequest,
) -> EvaluateActionResponse:
    """Pre-evaluate desktop action safety, triggering human review challenge if critical."""
    return default_desktop_enclave_service.evaluate_action(request)


@router.post("/decide", response_model=ChallengeDecisionResponse)
async def decide_enclave_challenge(
    request: ChallengeDecisionRequest,
) -> ChallengeDecisionResponse:
    """Submit human approval or rejection for an intercepted desktop action challenge."""
    return default_desktop_enclave_service.decide_challenge(request)


@router.post("/panic", response_model=PanicStatusResponse)
async def trigger_emergency_panic(
    request: PanicTriggerRequest,
) -> PanicStatusResponse:
    """Activate instant emergency panic stop, blocking all desktop actions."""
    return default_desktop_enclave_service.trigger_panic(reason=request.reason)


@router.post("/panic/reset", response_model=PanicStatusResponse)
async def reset_emergency_panic() -> PanicStatusResponse:
    """Reset emergency panic stop, restoring normal execution."""
    return default_desktop_enclave_service.reset_panic()


@router.get("/panic/status", response_model=PanicStatusResponse)
async def get_emergency_panic_status() -> PanicStatusResponse:
    """Check current state of emergency panic circuit breaker."""
    return default_desktop_enclave_service.get_panic_status()


@router.get("/challenges/pending", response_model=list[ActionEnclaveChallengeDto])
async def list_pending_challenges() -> list[ActionEnclaveChallengeDto]:
    """Retrieve all pending desktop action challenges awaiting human review."""
    return default_desktop_enclave_service.get_pending_challenges()


@router.get("/live-hud", response_model=LiveIntentFeedResponse)
async def get_live_intent_hud(
    limit: int = Query(default=20, ge=1, le=100),
) -> LiveIntentFeedResponse:
    """Get real-time Live Intent HUD telemetry projection for UI overlays."""
    return default_desktop_enclave_service.get_live_intent_feed(limit=limit)
