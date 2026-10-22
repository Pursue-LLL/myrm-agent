"""
[POS] app/api/agents/agent_handoff_router.py
[INPUT] fastapi, app/schemas/agent_handoff.py, app/services/agent/agent_handoff_service.py
[OUTPUT] router

FastAPI router exposing typed cross-agent handoff memorandum persistence and CAS claim endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from myrm_agent_harness.toolkits.memory.handoff import (
    HandoffAlreadyClaimedError,
    HandoffAlreadyCompletedError,
    HandoffInvalidTransitionError,
    HandoffNotFoundError,
    HandoffTargetMismatchError,
    SessionFinalizationError,
)

from app.schemas.agent_handoff import (
    AgentHandoffSpecDTO,
    CancelHandoffRequestDTO,
    ClaimHandoffRequestDTO,
    CompleteHandoffRequestDTO,
    CreateInChatHandoffRequestDTO,
    FinalizeSessionRequestDTO,
    FinalizeSessionResponseDTO,
    HandoffActionRequestDTO,
    HandoffAdvanceStageRequestDTO,
    HandoffClaimReceiptDTO,
    HandoffListResponseDTO,
    InChatHandoffCardDTO,
)
from app.services.agent.agent_handoff_service import (
    AgentHandoffService,
    get_agent_handoff_service,
)

router = APIRouter()


@router.post(
    "/handoff/finalize",
    response_model=FinalizeSessionResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Finalize active session and write durable handoff memorandum",
)
def finalize_session(
    request: FinalizeSessionRequestDTO,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> FinalizeSessionResponseDTO:
    """Finalize active session context into a durable, typed handoff record."""
    try:
        return service.finalize_session(request)
    except SessionFinalizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/handoff/{handoff_id}/claim",
    response_model=HandoffClaimReceiptDTO,
    status_code=status.HTTP_200_OK,
    summary="Atomically claim an open handoff memorandum (CAS exactly-once)",
)
def claim_handoff(
    handoff_id: str,
    request: ClaimHandoffRequestDTO,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> HandoffClaimReceiptDTO:
    """Acquire exclusive ownership of a pending handoff specification."""
    try:
        return service.claim_handoff(handoff_id=handoff_id, req=request)
    except HandoffNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HandoffAlreadyClaimedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except HandoffAlreadyCompletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except HandoffTargetMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except HandoffInvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/handoff/{handoff_id}/complete",
    response_model=AgentHandoffSpecDTO,
    status_code=status.HTTP_200_OK,
    summary="Mark a claimed handoff memorandum as completed",
)
def complete_handoff(
    handoff_id: str,
    request: CompleteHandoffRequestDTO,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> AgentHandoffSpecDTO:
    """Complete a claimed handoff memorandum by the authorized session."""
    try:
        return service.complete_handoff(handoff_id=handoff_id, req=request)
    except HandoffNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HandoffInvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/handoff/{handoff_id}/cancel",
    response_model=AgentHandoffSpecDTO,
    status_code=status.HTTP_200_OK,
    summary="Cancel a pending or claimed handoff",
)
def cancel_handoff(
    handoff_id: str,
    request: CancelHandoffRequestDTO,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> AgentHandoffSpecDTO:
    """Cancel a pending or claimed handoff memorandum."""
    try:
        return service.cancel_handoff(handoff_id=handoff_id, req=request)
    except HandoffNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HandoffAlreadyCompletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/handoff/pending",
    response_model=HandoffListResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List all pending handoffs eligible for claim",
)
def list_pending_handoffs(
    target_profile_id: str | None = Query(default=None, description="Optional target profile filter"),
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> HandoffListResponseDTO:
    """Retrieve all pending handoffs, optionally matching designated profile."""
    return service.list_pending(target_profile_id=target_profile_id)


@router.get(
    "/handoff/session/{session_id}",
    response_model=HandoffListResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List all handoffs associated with a session",
)
def list_session_handoffs(
    session_id: str,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> HandoffListResponseDTO:
    """Retrieve all handoff records created or claimed by a session."""
    return service.list_by_session(session_id=session_id)


# --- In-Chat Bot Task Handoff Delegation Endpoints ---


@router.post(
    "/handoff/in-chat",
    response_model=InChatHandoffCardDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate in-chat task delegation to a specialist bot",
)
def create_in_chat_handoff(
    request: CreateInChatHandoffRequestDTO,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> InChatHandoffCardDTO:
    """Create in-chat handoff card with five-stage orchestration lifecycle."""
    return service.create_in_chat_handoff(request)


@router.get(
    "/handoff/in-chat",
    response_model=list[InChatHandoffCardDTO],
    status_code=status.HTTP_200_OK,
    summary="List in-chat handoffs by session",
)
def list_in_chat_handoffs(
    session_id: str | None = Query(default=None, description="Optional chat session identifier filter"),
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> list[InChatHandoffCardDTO]:
    """Retrieve all in-chat bot handoffs for a given session."""
    return service.list_in_chat_handoffs(session_id=session_id)


@router.get(
    "/handoff/in-chat/{handoff_id}",
    response_model=InChatHandoffCardDTO,
    status_code=status.HTTP_200_OK,
    summary="Get in-chat handoff delegation card status",
)
def get_in_chat_handoff(
    handoff_id: str,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> InChatHandoffCardDTO:
    """Fetch live status of an in-chat bot handoff card."""
    card = service.get_in_chat_handoff(handoff_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"In-chat handoff '{handoff_id}' was not found.",
        )
    return card


@router.post(
    "/handoff/in-chat/{handoff_id}/action",
    response_model=InChatHandoffCardDTO,
    status_code=status.HTTP_200_OK,
    summary="Trigger human approval gate or completion CTA on in-chat handoff",
)
def trigger_in_chat_handoff_action(
    handoff_id: str,
    request: HandoffActionRequestDTO,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> InChatHandoffCardDTO:
    """Execute approval gate or post-delivery action (approve/reject/send_to_pr/accept)."""
    try:
        return service.handle_handoff_action(handoff_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/handoff/in-chat/{handoff_id}/advance-stage",
    response_model=InChatHandoffCardDTO,
    status_code=status.HTTP_200_OK,
    summary="Advance lifecycle stage in BkashJosi Five-Stage Stack",
)
def advance_in_chat_handoff_stage(
    handoff_id: str,
    request: HandoffAdvanceStageRequestDTO,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> InChatHandoffCardDTO:
    """Update progress and deliverables for a lifecycle stage."""
    try:
        return service.advance_stage(handoff_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# --- Generic Handoff Memorandum Endpoints ---


@router.get(
    "/handoff/{handoff_id}",
    response_model=AgentHandoffSpecDTO,
    status_code=status.HTTP_200_OK,
    summary="Get a specific handoff memorandum by ID",
)
def get_handoff(
    handoff_id: str,
    service: AgentHandoffService = Depends(get_agent_handoff_service),
) -> AgentHandoffSpecDTO:
    """Fetch complete snapshot of an agent handoff by unique ID."""
    spec = service.get_handoff(handoff_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Handoff '{handoff_id}' was not found.",
        )
    return spec

