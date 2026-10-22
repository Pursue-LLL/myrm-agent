"""Bot Mode Group Chat & Peer Messaging API Router.

[INPUT]
- GroupRoomCreateRequest, GroupMessageSendRequest, AgentPeerMessageRequest
- GroupRoom, GroupMessage, AgentPeerMessageResponse, PeerSessionArchive
- group_chat_service singleton

[OUTPUT]
- router: APIRouter for group chat rooms, mention orchestration, and Hermes peer parity

[POS]
app/api/chats/group_chat_router.py: REST endpoints for multi-bot room collaboration,
composer @-mention dispatch, and agent-to-agent peer consultation archiving.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.services.chat.group import (
    AgentPeerMessageRequest,
    AgentPeerMessageResponse,
    GroupMessage,
    GroupMessageSendRequest,
    GroupRoom,
    GroupRoomCreateRequest,
    PeerSessionArchive,
    group_chat_service,
)

router = APIRouter(prefix="/group-chat", tags=["Bot Mode Group Chat & Peer"])


@router.get(
    "/rooms",
    response_model=list[GroupRoom],
    status_code=status.HTTP_200_OK,
    summary="List all collaborative multi-bot rooms",
)
def list_group_rooms() -> list[GroupRoom]:
    """Retrieve all multi-bot group chat rooms."""
    return group_chat_service.list_rooms()


@router.post(
    "/rooms",
    response_model=GroupRoom,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new collaborative multi-bot room",
)
def create_group_room(req: GroupRoomCreateRequest) -> GroupRoom:
    """Create a new room with invited agent profiles."""
    return group_chat_service.create_room(req)


@router.get(
    "/rooms/{room_id}",
    response_model=GroupRoom,
    status_code=status.HTTP_200_OK,
    summary="Get details and timeline of a specific group room",
)
def get_group_room(room_id: str) -> GroupRoom:
    """Fetch room state and full timeline messages."""
    room = group_chat_service.get_room(room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group room '{room_id}' not found",
        )
    return room


@router.post(
    "/rooms/{room_id}/messages",
    response_model=list[GroupMessage],
    status_code=status.HTTP_200_OK,
    summary="Post message and dispatch replies for mentioned bots",
)
def post_group_message(
    room_id: str,
    req: GroupMessageSendRequest,
) -> list[GroupMessage]:
    """Post message into room and trigger sequential replies for @-mentioned agents."""
    messages = group_chat_service.post_message(room_id, req)
    if not messages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group room '{room_id}' not found",
        )
    return messages


@router.post(
    "/peer/direct-message",
    response_model=AgentPeerMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Agent-to-agent peer consultation with canonical archiving (Hermes peer parity)",
)
def send_peer_direct_message(
    req: AgentPeerMessageRequest,
) -> AgentPeerMessageResponse:
    """Consult another agent directly and automatically archive dialogue into canonical Bot Chat."""
    return group_chat_service.send_peer_message(req)


@router.get(
    "/peer/archives/{agent_id}",
    response_model=list[PeerSessionArchive],
    status_code=status.HTTP_200_OK,
    summary="List canonical peer session archives for a specific agent",
)
def list_agent_peer_archives(agent_id: str) -> list[PeerSessionArchive]:
    """Retrieve all archived peer conversations for an agent's canonical inbox."""
    return group_chat_service.list_peer_archives(agent_id)
