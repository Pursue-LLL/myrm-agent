"""FastAPI router for Multi-Human Multi-Agent Collaborative Virtual Room (Item 59).

[INPUT]
- app.schemas.virtual_room::{
    CreateRoomRequest, JoinRoomRequest, LeaveRoomRequest, AcquireFileLockRequest,
    ReleaseFileLockRequest, CreateBorrowingGrantRequest, DelegateExecutionRequest,
    RevokeBorrowingGrantRequest, RegisterServiceRelayRequest,
  }
- app.services.agent.virtual_room_service::{
    VirtualRoomService, get_virtual_room_service,
  }

[OUTPUT]
- REST endpoints under /agents/virtual-room for collaborative room management,
  in-flight VFS block locks, zero-credential agent borrowing, and port preview relays.

[POS]
- HTTP API layer for Item 59 Tutti-style real-time multi-human multi-agent co-dev.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.virtual_room import (
    AcquireFileLockRequest,
    CreateBorrowingGrantRequest,
    CreateRoomRequest,
    DelegateExecutionRequest,
    JoinRoomRequest,
    LeaveRoomRequest,
    RegisterServiceRelayRequest,
    ReleaseFileLockRequest,
    RevokeBorrowingGrantRequest,
)
from app.services.agent.virtual_room_service import (
    VirtualRoomService,
    get_virtual_room_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/virtual-room",
    tags=["Subagent Virtual Room & Filesystem Co-Dev"],
)


@router.post(
    "/rooms",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new collaborative virtual room workspace",
)
async def create_room(
    req: CreateRoomRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Initialize a persistent virtual room for multi-human multi-agent collaboration."""
    try:
        room_state = service.create_room(req)
        return create_success_response(data=room_state.model_dump())
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/rooms",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List all active collaborative virtual rooms",
)
async def list_rooms(
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Retrieve metadata states for all collaborative rooms."""
    rooms = service.list_rooms()
    return create_success_response(data=[r.model_dump() for r in rooms])


@router.get(
    "/rooms/{room_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unified state snapshot of a collaborative room",
)
async def get_room(
    room_id: str,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Retrieve full room snapshot including participants, VFS locks, and service relays."""
    try:
        state = service.get_room_state(room_id)
        return create_success_response(data=state.model_dump())
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_id}' not found",
        ) from err


@router.post(
    "/rooms/{room_id}/join",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Join a collaborative room as a human or AI agent",
)
async def join_room(
    room_id: str,
    req: JoinRoomRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Register participant with local identity boundary in the room."""
    try:
        participant = service.join_room(room_id, req)
        return create_success_response(data=participant.model_dump())
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_id}' not found",
        ) from err


@router.post(
    "/rooms/{room_id}/leave",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Leave a collaborative room",
)
async def leave_room(
    room_id: str,
    req: LeaveRoomRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Deactivate participant within the room."""
    success = service.leave_room(room_id, req)
    return create_success_response(data={"success": success})


@router.post(
    "/locks/acquire",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Acquire an in-flight file or line-range lease lock",
)
async def acquire_file_lock(
    req: AcquireFileLockRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Acquire fine-grained file block lease lock to prevent conflicting parallel writes."""
    try:
        lock = service.acquire_file_lock(req)
        return create_success_response(data=lock.model_dump())
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Filesystem lock conflict: {err}",
        ) from err


@router.post(
    "/locks/release",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Release an active in-flight lease lock",
)
async def release_file_lock(
    req: ReleaseFileLockRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Explicitly release held file lock."""
    try:
        success = service.release_file_lock(req)
        return create_success_response(data={"success": success})
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err)) from err


@router.get(
    "/locks",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List active in-flight filesystem locks",
)
async def list_active_locks(
    file_path: str | None = Query(None, description="Optional target file path filter"),
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Retrieve active write lease locks."""
    locks = service.list_active_locks(file_path=file_path)
    return create_success_response(data=[lk.model_dump() for lk in locks])


@router.post(
    "/grants/create",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a zero-credential agent capability borrowing grant",
)
async def create_borrowing_grant(
    req: CreateBorrowingGrantRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Authorize a teammate to borrow Agent capability without transferring API keys."""
    try:
        grant = service.create_borrowing_grant(req)
        return create_success_response(data=grant.model_dump())
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/grants/delegate",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Delegate task execution through a borrowed agent",
)
async def delegate_execution(
    req: DelegateExecutionRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Execute task using borrowed agent capability under token quota checks."""
    try:
        ok, result, used_tokens = service.delegate_execution(req)
        return create_success_response(
            data={"success": ok, "output": result, "used_tokens": used_tokens}
        )
    except KeyError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/grants/revoke",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke an agent borrowing grant",
)
async def revoke_borrowing_grant(
    req: RevokeBorrowingGrantRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Instantly terminate a capability grant by owner."""
    try:
        grant = service.revoke_borrowing_grant(req)
        return create_success_response(data=grant.model_dump())
    except KeyError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except PermissionError as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err)) from err


@router.post(
    "/relays/register",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a live preview port relay for the room",
)
async def register_service_relay(
    req: RegisterServiceRelayRequest,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Publish an internal sandbox port as room-wide accessible URL."""
    try:
        relay = service.register_service_relay(req)
        return create_success_response(data=relay.model_dump())
    except (KeyError, ValueError) as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/rooms/{room_id}/events",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List persistent organization activity events for a room",
)
async def list_activity_events(
    room_id: str,
    service: VirtualRoomService = Depends(get_virtual_room_service),
) -> StandardSuccessResponse:
    """Retrieve chronological audit memory log for the collaborative room."""
    events = service.list_activity_events(room_id)
    return create_success_response(data=[e.model_dump() for e in events])
