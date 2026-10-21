"""FastAPI router for Zero-Token Fleet Runtime Event Mirror Contract (Item 48).

[INPUT]
- app.schemas.zero_token_contract::{
    MirrorEventRequest,
    BatchMirrorEventRequest,
    LlmCallCheckRequest,
    SimulateViolationRequest,
  }
- app.services.agent.zero_token_contract_service::{
    ZeroTokenContractService,
    zero_token_contract_service,
  }

[OUTPUT]
- REST endpoints under /chats/{chat_id}/zero-token for event mirroring,
  Doctor LLM intercepting, and audit telemetry.

[POS]
- HTTP API layer for Zero-Token Contract.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.zero_token_contract import (
    BatchMirrorEventRequest,
    LlmCallCheckRequest,
    MirrorEventRequest,
    SimulateViolationRequest,
)
from app.services.agent.zero_token_contract_service import (
    ZeroTokenContractService,
    zero_token_contract_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Zero-Token Fleet Visualization Contract"])


def get_service() -> ZeroTokenContractService:
    """Dependency injector for ZeroTokenContractService."""
    return zero_token_contract_service


@router.post(
    "/chats/{chat_id}/zero-token/mirror",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Mirror a runtime event deterministically to visualization layer (0 tokens)",
)
def mirror_event_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: MirrorEventRequest = ...,
    service: ZeroTokenContractService = Depends(get_service),
) -> StandardSuccessResponse:
    """Consumes a runtime SSE/webhook event and updates visualization state with 0 tokens spent."""
    snapshot = service.mirror_event(chat_id=chat_id, request=payload)
    return create_success_response(data=snapshot.model_dump())


@router.post(
    "/chats/{chat_id}/zero-token/mirror-batch",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch mirror multiple runtime events deterministically (0 tokens)",
)
def mirror_batch_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: BatchMirrorEventRequest = ...,
    service: ZeroTokenContractService = Depends(get_service),
) -> StandardSuccessResponse:
    """Batch updates visualization projections from an event stream with 0 tokens spent."""
    snapshot = service.mirror_batch_events(chat_id=chat_id, request=payload)
    return create_success_response(data=snapshot.model_dump())


@router.post(
    "/chats/{chat_id}/zero-token/check-llm",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Doctor guard: Inspect and intercept unauthorized LLM calls from viz surfaces",
)
def check_llm_call_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: LlmCallCheckRequest = ...,
    service: ZeroTokenContractService = Depends(get_service),
) -> StandardSuccessResponse:
    """Inspects an LLM call request and blocks it if initiated from a protected viz surface."""
    result = service.check_or_intercept_llm_call(chat_id=chat_id, request=payload)
    return create_success_response(data=result.model_dump())


@router.get(
    "/chats/{chat_id}/zero-token/audit",
    response_model=StandardSuccessResponse,
    summary="Get Zero-Token contract compliance and audit snapshot",
)
def get_audit_report_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    service: ZeroTokenContractService = Depends(get_service),
) -> StandardSuccessResponse:
    """Retrieves metrics proving zero tokens spent by the visualization layer."""
    report = service.get_audit_report(chat_id=chat_id)
    return create_success_response(data=report.model_dump())


@router.post(
    "/chats/{chat_id}/zero-token/simulate-violation",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Exercise Doctor interception by simulating a visualization-to-LLM breach",
)
def simulate_violation_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: SimulateViolationRequest = ...,
    service: ZeroTokenContractService = Depends(get_service),
) -> StandardSuccessResponse:
    """Triggers a simulated contract violation to verify Doctor interception mechanisms."""
    check_resp, audit_report = service.simulate_violation(chat_id=chat_id, request=payload)
    return create_success_response(
        data={
            "intercept_result": check_resp.model_dump(),
            "updated_audit": audit_report.model_dump(),
        }
    )


@router.post(
    "/chats/{chat_id}/zero-token/reset",
    response_model=StandardSuccessResponse,
    summary="Reset Zero-Token audit ledger for session",
)
def reset_session_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    service: ZeroTokenContractService = Depends(get_service),
) -> StandardSuccessResponse:
    """Resets the audit ledger for test suites or fresh runs."""
    report = service.reset_session(chat_id=chat_id)
    return create_success_response(data=report.model_dump())
