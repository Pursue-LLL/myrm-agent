"""
[POS] app/api/security/bot_screen_intervention_router.py
[INPUT] fastapi, app.schemas.bot_screen_intervention, app.services.security.bot_screen_intervention_service
[OUTPUT] router

FastAPI router for Bot Screen Auditable Operational Control & Intervention Evidence Suite.
Exposes endpoints for least-privilege boundary enforcement, human takeover recording,
cryptographic audit evidence retrieval, and post-action UI assertion probes.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status

from app.schemas.bot_screen_intervention import (
    BotScreenOperationalMetricsResponse,
    ClassifyElementRiskRequest,
    ClassifyElementRiskResponse,
    EvaluateScreenActionRequest,
    EvaluateScreenActionResponse,
    InterventionEventResponse,
    InterventionEvidenceBundleResponse,
    RecordInterventionEventRequest,
    ScreenAssertionProbeResponse,
    SealEvidenceBundleRequest,
    StartInterventionRequest,
    StartInterventionResponse,
    VerifyScreenAssertionRequest,
)
from app.services.security.bot_screen_intervention_service import (
    BotScreenInterventionService,
    get_bot_screen_intervention_service,
)

router = APIRouter(
    prefix="/bot-screen-intervention",
    tags=["Bot Screen Auditable Operational Control & Intervention Evidence"],
)


@router.post(
    "/classify-element-risk",
    response_model=ClassifyElementRiskResponse,
    status_code=status.HTTP_200_OK,
    summary="Classify UI screen element into an operational risk tier",
)
def classify_element_risk(
    request: ClassifyElementRiskRequest,
    service: BotScreenInterventionService = Depends(get_bot_screen_intervention_service),
) -> ClassifyElementRiskResponse:
    """Classify screen element risk based on element selector, action type, and label."""
    return service.classify_element_risk(request)


@router.post(
    "/evaluate-action",
    response_model=EvaluateScreenActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate intended screen action against least-privilege enterprise boundary rules",
)
def evaluate_action(
    request: EvaluateScreenActionRequest,
    service: BotScreenInterventionService = Depends(get_bot_screen_intervention_service),
) -> EvaluateScreenActionResponse:
    """Evaluate whether an intended UI action is approved, requires approval, or mandates manual takeover."""
    return service.evaluate_action(request)


@router.post(
    "/interventions/start",
    response_model=StartInterventionResponse,
    status_code=status.HTTP_200_OK,
    summary="Start recorded human takeover session",
)
def start_intervention(
    request: StartInterventionRequest,
    service: BotScreenInterventionService = Depends(get_bot_screen_intervention_service),
) -> StartInterventionResponse:
    """Initialize tamper-evident event log for human takeover intervention."""
    return service.start_intervention(request)


@router.post(
    "/interventions/record-event",
    response_model=InterventionEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Record operator input event during human takeover",
)
def record_event(
    request: RecordInterventionEventRequest,
    service: BotScreenInterventionService = Depends(get_bot_screen_intervention_service),
) -> InterventionEventResponse:
    """Record keystroke or mouse event with sensitive credential scrubbing."""
    return service.record_event(request)


@router.post(
    "/interventions/seal",
    response_model=InterventionEvidenceBundleResponse,
    status_code=status.HTTP_200_OK,
    summary="Seal tamper-proof cryptographic evidence bundle upon handover back to agent",
)
def seal_evidence_bundle(
    request: SealEvidenceBundleRequest,
    service: BotScreenInterventionService = Depends(get_bot_screen_intervention_service),
) -> InterventionEvidenceBundleResponse:
    """Close active human takeover and seal cryptographic SHA-256 evidence bundle."""
    return service.seal_evidence_bundle(request)


@router.get(
    "/interventions/{intervention_id}",
    response_model=InterventionEvidenceBundleResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve sealed tamper-proof audit bundle by intervention ID",
)
def get_evidence_bundle(
    intervention_id: str = Path(..., description="Unique intervention identifier"),
    service: BotScreenInterventionService = Depends(get_bot_screen_intervention_service),
) -> InterventionEvidenceBundleResponse:
    """Query sealed audit bundle for legal and compliance inspection."""
    return service.get_evidence_bundle(intervention_id)


@router.post(
    "/assertions/verify",
    response_model=ScreenAssertionProbeResponse,
    status_code=status.HTTP_200_OK,
    summary="Run autonomous DOM and visual snapshot assertion probe",
)
def verify_screen_assertion(
    request: VerifyScreenAssertionRequest,
    service: BotScreenInterventionService = Depends(get_bot_screen_intervention_service),
) -> ScreenAssertionProbeResponse:
    """Assert UI outcome against expected DOM content and visual snapshot."""
    return service.verify_screen_assertion(request)


@router.get(
    "/metrics",
    response_model=BotScreenOperationalMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve cumulative metrics for screen operations and takeover audits",
)
def get_metrics(
    service: BotScreenInterventionService = Depends(get_bot_screen_intervention_service),
) -> BotScreenOperationalMetricsResponse:
    """Get metrics tracking actions, checkpoints, manual takeovers, and evidence bundles."""
    return service.get_metrics()
