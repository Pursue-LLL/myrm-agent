"""FastAPI router for One-Model Multi-Agent Shared Context Token Budget Governance (Item 52).

[INPUT]
- app.schemas.token_budget_governance::{
    RegisterRoleBudgetRequest,
    GovernancePrecheckRequest,
    RecordConsumptionRequest,
  }
- app.services.agent.token_budget_governance_service::{
    TokenBudgetGovernanceService,
    get_token_budget_governance_service,
  }

[OUTPUT]
- REST endpoints under /chats/{chat_id}/token-governance for role budget declarations,
  fan-out precheck, consumption ledger logging, and Doctor Nudge warnings.

[POS]
- HTTP API layer for token budget governance & routing overhead visualization.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, Query, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.token_budget_governance import (
    GovernancePrecheckRequest,
    RecordConsumptionRequest,
    RegisterRoleBudgetRequest,
)
from app.services.agent.token_budget_governance_service import (
    TokenBudgetGovernanceService,
    get_token_budget_governance_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["One-Model Multi-Agent Shared Context Token Budget Governance"])


def get_service() -> TokenBudgetGovernanceService:
    """Dependency injector for TokenBudgetGovernanceService."""
    return get_token_budget_governance_service()


@router.post(
    "/chats/{chat_id}/token-governance/roles",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update a per-role token budget ceiling and stop condition",
)
def register_role_budget_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: RegisterRoleBudgetRequest = ...,
    service: TokenBudgetGovernanceService = Depends(get_service),
) -> StandardSuccessResponse:
    spec = service.register_role_budget(session_id=chat_id, request=payload)
    return create_success_response(data=spec.model_dump())


@router.post(
    "/chats/{chat_id}/token-governance/precheck",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Precheck fan-out budget before scheduling a turn to a role",
)
def precheck_fanout_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: GovernancePrecheckRequest = ...,
    service: TokenBudgetGovernanceService = Depends(get_service),
) -> StandardSuccessResponse:
    res = service.precheck_fanout(session_id=chat_id, request=payload)
    return create_success_response(data=res.model_dump())


@router.post(
    "/chats/{chat_id}/token-governance/consumption",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Record token consumption categorized by routing overhead vs execution payload",
)
def record_consumption_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: RecordConsumptionRequest = ...,
    service: TokenBudgetGovernanceService = Depends(get_service),
) -> StandardSuccessResponse:
    record = service.record_consumption(session_id=chat_id, request=payload)
    return create_success_response(data=record.model_dump())


@router.get(
    "/chats/{chat_id}/token-governance/snapshot",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get global token budget snapshot, routing breakdown, and active Doctor alerts",
)
def get_snapshot_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    service: TokenBudgetGovernanceService = Depends(get_service),
) -> StandardSuccessResponse:
    snapshot = service.get_snapshot(session_id=chat_id)
    return create_success_response(data=snapshot.model_dump())


@router.get(
    "/chats/{chat_id}/token-governance/doctor-nudges",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve active Doctor Nudge budget and routing warnings",
)
def get_doctor_nudges_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    threshold_routing_ratio: float = Query(
        default=0.35, ge=0.05, le=0.95, description="Routing overhead ratio threshold"
    ),
    max_handoffs: int = Query(default=5, ge=1, le=50, description="Max allowed handoffs"),
    service: TokenBudgetGovernanceService = Depends(get_service),
) -> StandardSuccessResponse:
    alerts = service.evaluate_doctor_nudge(
        session_id=chat_id,
        threshold_routing_ratio=threshold_routing_ratio,
        max_handoffs=max_handoffs,
    )
    return create_success_response(data=[a.model_dump() for a in alerts])


@router.post(
    "/chats/{chat_id}/token-governance/reset",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset token budget governance state for this session",
)
def reset_token_governance_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    service: TokenBudgetGovernanceService = Depends(get_service),
) -> StandardSuccessResponse:
    service.reset_session(session_id=chat_id)
    return create_success_response(data={"message": f"Session '{chat_id}' token budget governance reset successfully."})
