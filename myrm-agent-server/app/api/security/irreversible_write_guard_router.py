"""FastAPI router for Pre-Flight Irreversible Write Interception and Emergency Kill Switch.

[INPUT]
- HTTP requests via FastAPI for tool call interception, intent approval, and emergency kill switch.

[OUTPUT]
- APIRouter exposing endpoints for pre-flight irreversible write governance.

[POS]
API presentation layer for irreversible write guard interception and contract review.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.irreversible_write_guard import (
    ApproveIntentRequest,
    ContractResponse,
    EmergencyKillRequest,
    EmergencyKillResponse,
    InterceptToolCallRequest,
    InterceptToolCallResponse,
    IrreversibleWriteIntentResponse,
    RegisterContractRequest,
)
from app.services.security.irreversible_write_guard_service import (
    IrreversibleWriteGuardService,
    get_irreversible_write_guard_service,
)

router = APIRouter(prefix="/irreversible-write-guard", tags=["irreversible-write-guard"])


@router.post(
    "/intercept",
    response_model=InterceptToolCallResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate tool call for irreversible external write side-effects",
)
def intercept_tool_call(
    request: InterceptToolCallRequest,
    service: IrreversibleWriteGuardService = Depends(get_irreversible_write_guard_service),
) -> InterceptToolCallResponse:
    """Check tool name and arguments against irreversible write contracts. Suspend if matched."""
    return service.intercept_tool_call(request)


@router.post(
    "/approve/{intent_id}",
    response_model=IrreversibleWriteIntentResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve a suspended irreversible write operation for dispatch",
)
def approve_intent(
    intent_id: str,
    request: ApproveIntentRequest,
    service: IrreversibleWriteGuardService = Depends(get_irreversible_write_guard_service),
) -> IrreversibleWriteIntentResponse:
    """Authorize a suspended intent following blast radius review."""
    try:
        return service.approve_intent(intent_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Intent '{intent_id}' not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/kill/{intent_id}",
    response_model=EmergencyKillResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger emergency kill switch to abort and destroy pending action",
)
def emergency_kill(
    intent_id: str,
    request: EmergencyKillRequest,
    service: IrreversibleWriteGuardService = Depends(get_irreversible_write_guard_service),
) -> EmergencyKillResponse:
    """Abort an intercepted action immediately and zero out its payload."""
    try:
        return service.emergency_kill(intent_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Intent '{intent_id}' not found.",
        ) from exc


@router.get(
    "/intents/{intent_id}",
    response_model=IrreversibleWriteIntentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get intent status and blast radius details",
)
def get_intent(
    intent_id: str,
    service: IrreversibleWriteGuardService = Depends(get_irreversible_write_guard_service),
) -> IrreversibleWriteIntentResponse:
    """Retrieve full details of an intent by ID."""
    intent = service.get_intent(intent_id)
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Intent '{intent_id}' not found.",
        )
    return intent


@router.get(
    "/pending",
    response_model=list[IrreversibleWriteIntentResponse],
    status_code=status.HTTP_200_OK,
    summary="List active pending confirmation intents",
)
def list_pending(
    session_id: str | None = Query(default=None),
    service: IrreversibleWriteGuardService = Depends(get_irreversible_write_guard_service),
) -> list[IrreversibleWriteIntentResponse]:
    """Retrieve all pending intents awaiting blast radius review."""
    return service.list_pending(session_id)


@router.get(
    "/contracts",
    response_model=list[ContractResponse],
    status_code=status.HTTP_200_OK,
    summary="List registered irreversible write tool contracts",
)
def list_contracts(
    service: IrreversibleWriteGuardService = Depends(get_irreversible_write_guard_service),
) -> list[ContractResponse]:
    """List standard and custom tool contracts."""
    return service.list_contracts()


@router.post(
    "/contracts",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new irreversible write tool contract",
)
def register_contract(
    request: RegisterContractRequest,
    service: IrreversibleWriteGuardService = Depends(get_irreversible_write_guard_service),
) -> ContractResponse:
    """Register custom tool contract."""
    try:
        return service.register_contract(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid contract parameters: {exc}",
        ) from exc
