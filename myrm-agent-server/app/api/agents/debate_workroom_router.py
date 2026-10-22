"""[INPUT] chat_id, room_id, request bodies from schemas/debate_workroom.py, and DebateWorkroomService.
[OUTPUT] StandardSuccessResponse containing DebateRoomResponse, DebateTurnDTO, or OperationStatusResponse.
[POS] FastAPI router for Multi-Agent Debate Workroom & Kanban Integration.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.debate_workroom import (
    AdvancePhaseRequest,
    CreateDebateRoomRequest,
    DecomposeTaskRequest,
    OperationStatusResponse,
    PostArgumentRequest,
    SyncKanbanSubtaskRequest,
    SynthesizeDecisionRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.debate_workroom_service import DebateWorkroomService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/debate-workrooms", tags=["Debate Workroom"])


def get_debate_workroom_service() -> DebateWorkroomService:
    """Dependency injector for DebateWorkroomService singleton."""
    return DebateWorkroomService.get_instance()


@router.post(
    "",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new multi-agent debate workroom",
)
def create_debate_room_endpoint(
    chat_id: str,
    req: CreateDebateRoomRequest,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """Initialize a multi-agent debate workroom in decomposition phase."""
    room = service.create_room(chat_id=chat_id, request=req)
    return create_success_response(data=room)


@router.get(
    "",
    response_model=StandardSuccessResponse,
    summary="List all debate workrooms for a chat",
)
def list_debate_rooms_endpoint(
    chat_id: str,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """List active debate workrooms associated with the chat session."""
    rooms = service.list_rooms(chat_id=chat_id)
    return create_success_response(data=rooms)


@router.get(
    "/{room_id}",
    response_model=StandardSuccessResponse,
    summary="Get state of a specific debate workroom",
)
def get_debate_room_endpoint(
    chat_id: str,
    room_id: str,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """Fetch complete debate state including participants, subtasks, turns, and consensus."""
    room = service.get_room(room_id=room_id)
    if not room or room.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate room not found: {room_id}",
        )
    return create_success_response(data=room)


@router.post(
    "/{room_id}/decompose",
    response_model=StandardSuccessResponse,
    summary="Leader decomposes root topic into assigned subtasks",
)
def decompose_task_endpoint(
    chat_id: str,
    room_id: str,
    req: DecomposeTaskRequest,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """Submit decomposed subtasks and transition room to round argument phase."""
    room = service.get_room(room_id=room_id)
    if not room or room.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate room not found: {room_id}",
        )
    updated = service.decompose(room_id=room_id, subtasks_dto=req.subtasks)
    return create_success_response(data=updated)


@router.post(
    "/{room_id}/argument",
    response_model=StandardSuccessResponse,
    summary="Post specialist argument or critique into debate stream",
)
def post_argument_endpoint(
    chat_id: str,
    room_id: str,
    req: PostArgumentRequest,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """Submit an argument, cross-examination, or evidence turn. Automatically enforces anti-wheel-war guard."""
    room = service.get_room(room_id=room_id)
    if not room or room.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate room not found: {room_id}",
        )
    turn = service.post_argument(room_id=room_id, request=req)
    return create_success_response(data=turn)


@router.post(
    "/{room_id}/advance-phase",
    response_model=StandardSuccessResponse,
    summary="Advance the debate phase",
)
def advance_phase_endpoint(
    chat_id: str,
    room_id: str,
    req: AdvancePhaseRequest,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """Advance workroom phase sequentially or jump to a specified target phase."""
    room = service.get_room(room_id=room_id)
    if not room or room.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate room not found: {room_id}",
        )
    updated = service.advance_phase(room_id=room_id, target_phase=req.target_phase)
    return create_success_response(data=updated)


@router.post(
    "/{room_id}/converge",
    response_model=StandardSuccessResponse,
    summary="Synthesize consensus decision and settle debate",
)
def converge_endpoint(
    chat_id: str,
    room_id: str,
    req: SynthesizeDecisionRequest,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """Record final consensus decision, mark specified subtasks as DONE, and settle room."""
    room = service.get_room(room_id=room_id)
    if not room or room.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate room not found: {room_id}",
        )
    settled = service.synthesize(
        room_id=room_id,
        consensus_decision=req.consensus_decision,
        settled_subtask_ids=req.settled_subtask_ids,
    )
    return create_success_response(data=settled)


@router.post(
    "/{room_id}/subtasks/{task_id}/kanban-sync",
    response_model=StandardSuccessResponse,
    summary="Sync subtask execution state with linked Kanban task",
)
def sync_kanban_subtask_endpoint(
    chat_id: str,
    room_id: str,
    task_id: str,
    req: SyncKanbanSubtaskRequest,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """Synchronize debate subtask status with a Kanban task card."""
    room = service.get_room(room_id=room_id)
    if not room or room.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate room not found: {room_id}",
        )
    try:
        updated = service.sync_kanban_subtask(
            room_id=room_id,
            task_id=task_id,
            kanban_task_id=req.kanban_task_id,
            kanban_status=req.kanban_status,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return create_success_response(data=updated)


@router.delete(
    "/{room_id}",
    response_model=StandardSuccessResponse,
    summary="Delete a debate workroom",
)
def delete_debate_room_endpoint(
    chat_id: str,
    room_id: str,
    service: DebateWorkroomService = Depends(get_debate_workroom_service),
) -> StandardSuccessResponse:
    """Remove a debate room from memory and release resources."""
    room = service.get_room(room_id=room_id)
    if not room or room.chat_id != chat_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate room not found: {room_id}",
        )
    success = service.delete_room(room_id=room_id)
    res = OperationStatusResponse(
        status="deleted" if success else "ok",
        room_id=room_id,
        message="Room deleted successfully",
    )
    return create_success_response(data=res)
