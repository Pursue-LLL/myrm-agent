"""
[POS] app/api/security/auto_review_resolution_router.py
[INPUT] app.schemas.auto_review_resolution, app.services.security.auto_review_resolution_service
[OUTPUT] router

FastAPI router for Auto-Review Denial Four-Way Adaptive Resolution State Machine Suite.
Exposes REST endpoints to generate denial diagnostics, evaluate 4-way resolution strategies,
stage and execute interactive human handover cards, and commit decisions.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.schemas.auto_review_resolution import (
    AutoReviewResolutionMetricsResponse,
    BranchEvaluationRequest,
    BranchEvaluationResponse,
    CommitResolutionRequest,
    DenialDiagnosticResponse,
    HandoverDeckResponse,
    ReportDenialRequest,
    ResolutionDecisionResponse,
    StageHandoverRequest,
)
from app.services.security.auto_review_resolution_service import (
    AutoReviewResolutionService,
    get_auto_review_resolution_service,
)

router = APIRouter(
    prefix="/auto-review-resolution",
    tags=["Auto-Review Denial 4-Way Adaptive Resolution & Handover"],
)


@router.post(
    "/report-denial",
    response_model=DenialDiagnosticResponse,
    status_code=status.HTTP_200_OK,
    summary="Construct structured diagnostic report and register denial in session state machine",
)
def report_denial(
    request: ReportDenialRequest,
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> DenialDiagnosticResponse:
    """Report an auto-review block and synthesize alternatives and branch guidance."""
    return service.report_denial(request)


@router.get(
    "/active-denial/{session_id}",
    response_model=DenialDiagnosticResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve active pending denial diagnostic for a session",
)
def get_active_denial(
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> DenialDiagnosticResponse:
    """Inspect current pending denial report."""
    diag = service.get_active_denial(session_id)
    if diag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active denial found for session '{session_id}'.",
        )
    return diag


@router.post(
    "/evaluate-branch",
    response_model=BranchEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate agent proposed resolution branch against isomorphic loop breaker",
)
def evaluate_branch(
    request: BranchEvaluationRequest,
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> BranchEvaluationResponse:
    """Check if proposed branch (Ask/Alternative/Handover/Stop) is permitted or loops are broken."""
    return service.evaluate_branch(request)


@router.post(
    "/handover",
    response_model=HandoverDeckResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Pre-stage contextual human handover execution card",
)
def stage_handover(
    request: StageHandoverRequest,
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> HandoverDeckResponse:
    """Stage pre-composed command and parameters for human one-click execution."""
    return service.stage_handover(request)


@router.get(
    "/handover/{handover_id}",
    response_model=HandoverDeckResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect status of staged handover deck",
)
def get_handover(
    handover_id: str = Path(..., min_length=1, description="Handover identifier"),
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> HandoverDeckResponse:
    """Retrieve handover card details."""
    deck = service.get_handover(handover_id)
    if deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Handover deck '{handover_id}' not found.",
        )
    return deck


@router.get(
    "/handovers",
    response_model=list[HandoverDeckResponse],
    status_code=status.HTTP_200_OK,
    summary="List active staged handover cards",
)
def list_staged_handovers(
    session_id: str | None = Query(default=None, description="Optional session filter"),
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> list[HandoverDeckResponse]:
    """List pending staged handover cards awaiting user release."""
    return service.list_staged_handovers(session_id)


@router.post(
    "/handover/{handover_id}/execute",
    response_model=HandoverDeckResponse,
    status_code=status.HTTP_200_OK,
    summary="Release and execute pre-staged handover card by human user",
)
def execute_handover(
    handover_id: str = Path(..., min_length=1, description="Handover identifier"),
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> HandoverDeckResponse:
    """Execute pre-staged command and transition card to EXECUTED_BY_USER."""
    deck = service.execute_handover(handover_id)
    if deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Handover deck '{handover_id}' not found or already completed.",
        )
    return deck


@router.post(
    "/handover/{handover_id}/dismiss",
    response_model=HandoverDeckResponse,
    status_code=status.HTTP_200_OK,
    summary="Dismiss or cancel staged handover card by human user",
)
def dismiss_handover(
    handover_id: str = Path(..., min_length=1, description="Handover identifier"),
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> HandoverDeckResponse:
    """Dismiss card and transition to DISMISSED_BY_USER."""
    deck = service.dismiss_handover(handover_id)
    if deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Handover deck '{handover_id}' not found or already completed.",
        )
    return deck


@router.post(
    "/commit-resolution",
    response_model=ResolutionDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Record agent final resolution branch decision for current denial",
)
def commit_resolution(
    request: CommitResolutionRequest,
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> ResolutionDecisionResponse:
    """Commit decision record and clear active denial slot."""
    return service.commit_resolution(request)


@router.get(
    "/history/{session_id}",
    response_model=list[ResolutionDecisionResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve audit trail of resolution decisions for a session",
)
def get_resolution_history(
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> list[ResolutionDecisionResponse]:
    """Inspect history of 4-way resolutions in session."""
    return service.get_resolution_history(session_id)


@router.get(
    "/metrics",
    response_model=AutoReviewResolutionMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect cumulative metrics for auto-review denial resolution",
)
def get_metrics(
    service: AutoReviewResolutionService = Depends(
        get_auto_review_resolution_service
    ),
) -> AutoReviewResolutionMetricsResponse:
    """Retrieve cumulative statistics across denial branches and handovers."""
    return service.get_metrics()
