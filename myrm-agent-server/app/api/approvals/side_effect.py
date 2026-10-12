"""REST API for Pre-Action Side-Effect Gate and Post-Run Deterministic Acceptance.

[INPUT]
- app.schemas.side_effect_gate schemas
- app.services.approvals.side_effect_gate_service
- app.services.approvals.post_run_acceptance_service

[OUTPUT]
- APIRouter mounted under /approvals/side-effects

[POS]
Server API. Provides endpoints for reviewing intercepted actions, issuing single-use
execution tokens, querying idempotency receipts, and evaluating deliverables.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path, status

from app.schemas.side_effect_gate import (
    AcceptanceEvaluationRequest,
    AcceptanceEvaluationResponse,
    ActionReceiptCreateRequest,
    ActionReceiptDto,
    PreActionChallengeDto,
    PreActionDecisionRequest,
    PreActionDecisionResponse,
)
from app.services.approvals.post_run_acceptance_service import (
    get_post_run_acceptance_service,
)
from app.services.approvals.side_effect_gate_service import (
    get_side_effect_gate_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/side-effects", tags=["approvals-side-effects"])


@router.get(
    "/pending",
    response_model=list[PreActionChallengeDto],
    summary="List intercepted pre-action challenges awaiting authorization",
)
async def list_pending_challenges() -> list[PreActionChallengeDto]:
    """Retrieve all unexpired, pending pre-action challenges."""
    service = get_side_effect_gate_service()
    return service.list_pending_challenges()


@router.get(
    "/{challenge_id}",
    response_model=PreActionChallengeDto,
    summary="Get challenge details by ID",
)
async def get_challenge(
    challenge_id: str = Path(..., description="Challenge ID"),
) -> PreActionChallengeDto:
    """Retrieve details of a specific pre-action challenge."""
    service = get_side_effect_gate_service()
    challenge = service.get_challenge(challenge_id)
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Challenge '{challenge_id}' not found",
        )
    return challenge


@router.post(
    "/{challenge_id}/decide",
    response_model=PreActionDecisionResponse,
    summary="Submit approval or rejection decision for an intercepted action",
)
async def decide_challenge(
    body: PreActionDecisionRequest,
    challenge_id: str = Path(..., description="Challenge ID"),
) -> PreActionDecisionResponse:
    """Authorize or reject an intercepted irreversible action."""
    service = get_side_effect_gate_service()
    response = service.decide_challenge(
        challenge_id=challenge_id,
        decision=body.decision,
        reviewer_id=body.reviewer_id,
        reason=body.reason,
    )
    if response.status == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=response.message,
        )
    return response


@router.post(
    "/receipts",
    response_model=ActionReceiptDto,
    status_code=status.HTTP_201_CREATED,
    summary="Record external execution receipt for idempotent replay",
)
async def record_receipt(body: ActionReceiptCreateRequest) -> ActionReceiptDto:
    """Record execution receipt from external vendor or provider."""
    service = get_side_effect_gate_service()
    return service.record_receipt(body)


@router.get(
    "/receipts/{idempotency_key}",
    response_model=ActionReceiptDto,
    summary="Query execution receipt by idempotency key",
)
async def get_receipt(
    idempotency_key: str = Path(..., description="Deterministic idempotency key"),
) -> ActionReceiptDto:
    """Retrieve an existing execution receipt."""
    service = get_side_effect_gate_service()
    receipt = service.get_receipt(idempotency_key)
    if receipt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No execution receipt found for key '{idempotency_key}'",
        )
    return receipt


@router.post(
    "/acceptance/evaluate",
    response_model=AcceptanceEvaluationResponse,
    summary="Run deterministic quality acceptance evaluation on deliverable",
)
async def evaluate_acceptance(
    body: AcceptanceEvaluationRequest,
) -> AcceptanceEvaluationResponse:
    """Evaluate deliverable against deterministic length, structure, and arithmetic rules."""
    service = get_post_run_acceptance_service()
    return service.evaluate(body)
