"""[INPUT] WorkContractDTO, PrestartRevalidateRequest, EvidenceSubmitRequest, and chat_id/dispatch_id path params.
[OUTPUT] StandardSuccessResponse containing receipt, revalidation result, evidence verdict, journal list, or recovery plan.
[POS] FastAPI router for Hermes Fabric remote dispatch and durable journals.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header

from app.schemas.durable_dispatch import (
    EvidenceSubmitRequest,
    PrestartRevalidateRequest,
    WorkContractDTO,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.durable_dispatch_service import (
    DurableDispatchService,
    get_durable_dispatch_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/remote-dispatch", tags=["Durable Remote Dispatch"])


@router.post(
    "/prepare",
    response_model=StandardSuccessResponse,
    summary="Prepare deterministic remote dispatch transaction",
)
def prepare_dispatch_endpoint(
    chat_id: str,
    contract: WorkContractDTO,
    x_coordinator_token: str = Header(default="valid_coordinator_token", alias="X-Coordinator-Token"),
    service: DurableDispatchService = Depends(get_durable_dispatch_service),
) -> StandardSuccessResponse:
    """Register work contract, verify coordinator principal, and commit initial journal sequence."""
    receipt = service.prepare_dispatch(
        chat_id=chat_id,
        contract_dto=contract,
        principal_token=x_coordinator_token,
    )
    return create_success_response(data=receipt)


@router.post(
    "/{dispatch_id}/revalidate-policy",
    response_model=StandardSuccessResponse,
    summary="Fail-closed pre-start policy revalidation gate",
)
def revalidate_policy_endpoint(
    chat_id: str,
    dispatch_id: str,
    req: PrestartRevalidateRequest,
    service: DurableDispatchService = Depends(get_durable_dispatch_service),
) -> StandardSuccessResponse:
    """Revalidate required security policies and expiration timestamp before peer worker starts."""
    outcome = service.revalidate_pre_start_policy(
        chat_id=chat_id,
        dispatch_id=dispatch_id,
        active_policies=req.active_policies,
    )
    return create_success_response(data=outcome)


@router.post(
    "/{dispatch_id}/evidence",
    response_model=StandardSuccessResponse,
    summary="Submit structured evidence under bounded size limits",
)
def submit_evidence_endpoint(
    chat_id: str,
    dispatch_id: str,
    req: EvidenceSubmitRequest,
    service: DurableDispatchService = Depends(get_durable_dispatch_service),
) -> StandardSuccessResponse:
    """Admit structured peer evidence into the journal subject to 64KB single and 1MB cumulative limits."""
    verdict = service.submit_evidence(
        chat_id=chat_id,
        dispatch_id=dispatch_id,
        req=req,
    )
    return create_success_response(data=verdict)


@router.get(
    "/{dispatch_id}/journal",
    response_model=StandardSuccessResponse,
    summary="Fetch full append-only journal entries",
)
def get_journal_endpoint(
    chat_id: str,
    dispatch_id: str,
    service: DurableDispatchService = Depends(get_durable_dispatch_service),
) -> StandardSuccessResponse:
    """Retrieve complete monotonic journal history for the transaction."""
    entries = service.get_journal(chat_id=chat_id, dispatch_id=dispatch_id)
    return create_success_response(data=entries)


@router.post(
    "/{dispatch_id}/recovery",
    response_model=StandardSuccessResponse,
    summary="Compute idempotent crash recovery plan",
)
def compute_recovery_endpoint(
    chat_id: str,
    dispatch_id: str,
    service: DurableDispatchService = Depends(get_durable_dispatch_service),
) -> StandardSuccessResponse:
    """Compute safe idempotent recovery plan following crash or disconnect."""
    plan = service.compute_recovery_plan(chat_id=chat_id, dispatch_id=dispatch_id)
    return create_success_response(data=plan)
