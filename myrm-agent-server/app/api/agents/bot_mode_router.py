"""FastAPI router for Bot Mode Named Profile Roster & Inter-Bot Mailbox Protocol (Item 33).

[INPUT]
- app.schemas.bot_mode::{RegisterBotRequest, SendBotMessageRequest, DispatchMentionsRequest, ...}
- app.services.agent.bot_mode_service::{BotModeService, get_bot_mode_service}

[OUTPUT]
- Router mounted under /chats/{chat_id}/bot-mode.

[POS]
- HTTP endpoints for managing named AI colleague workstations, peer-to-peer messaging,
  and @mention resolution relays.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.schemas.bot_mode import (
    BotStatusEnum,
    DispatchMentionsRequest,
    MarkReadRequest,
    RegisterBotRequest,
    SendBotMessageRequest,
    UpdateBotStatusRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.bot_mode_service import (
    BotModeService,
    get_bot_mode_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/bot-mode", tags=["Bot Mode Workstations"])


@router.post(
    "/register",
    response_model=StandardSuccessResponse,
    summary="Register or update an AI colleague workstation profile",
)
def register_bot_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    req: RegisterBotRequest = ...,
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Register a named bot with @handle, avatar seed, skills, and model tier."""
    profile = service.register_bot(session_id=chat_id, req=req)
    return create_success_response(data=profile)


@router.get(
    "/roster",
    response_model=StandardSuccessResponse,
    summary="List all AI colleague workstations in the roster",
)
def list_roster_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    status_filter: BotStatusEnum | None = Query(None, description="Optional status filter"),
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Retrieve full catalog of registered bots in the session."""
    roster = service.list_bots(session_id=chat_id, status_filter=status_filter)
    return create_success_response(data=roster)


@router.get(
    "/bots/{bot_id}",
    response_model=StandardSuccessResponse,
    summary="Get workstation profile details for a specific bot",
)
def get_bot_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    bot_id: str = Path(..., description="Bot ID or @handle"),
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Lookup a bot profile by bot_id or @handle."""
    profile = service.get_bot(session_id=chat_id, bot_id=bot_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Bot '{bot_id}' not found in roster")
    return create_success_response(data=profile)


@router.patch(
    "/bots/{bot_id}/status",
    response_model=StandardSuccessResponse,
    summary="Update availability status of a bot workstation",
)
def update_bot_status_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    bot_id: str = Path(..., description="Bot ID"),
    req: UpdateBotStatusRequest = ...,
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Update bot status (idle, busy, offline) and active task association."""
    profile = service.update_bot_status(session_id=chat_id, bot_id=bot_id, req=req)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Bot '{bot_id}' not found in roster")
    return create_success_response(data=profile)


@router.post(
    "/messages/send",
    response_model=StandardSuccessResponse,
    summary="Send a direct message from one bot to another",
)
def send_message_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    req: SendBotMessageRequest = ...,
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Deliver a message into the recipient bot's mailbox inbox."""
    try:
        msg = service.send_message(session_id=chat_id, req=req)
        return create_success_response(data=msg)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.post(
    "/messages/dispatch-mentions",
    response_model=StandardSuccessResponse,
    summary="Scan text for @mentions and dispatch to all matching bot workstations",
)
def dispatch_mentions_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    req: DispatchMentionsRequest = ...,
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Extract @mentions and route inbox messages accordingly."""
    results = service.dispatch_mentions(session_id=chat_id, req=req)
    return create_success_response(data=results)


@router.get(
    "/bots/{bot_id}/inbox",
    response_model=StandardSuccessResponse,
    summary="Retrieve messages in a bot's mailbox inbox",
)
def get_inbox_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    bot_id: str = Path(..., description="Bot ID or @handle"),
    unread_only: bool = Query(False, description="Filter to unread messages only"),
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Get inbox messages and unread counter for the target bot."""
    inbox = service.get_inbox(session_id=chat_id, bot_id=bot_id, unread_only=unread_only)
    if not inbox:
        raise HTTPException(status_code=404, detail=f"Bot '{bot_id}' not found in roster")
    return create_success_response(data=inbox)


@router.post(
    "/bots/{bot_id}/inbox/mark-read",
    response_model=StandardSuccessResponse,
    summary="Mark specific inbox messages as read",
)
def mark_read_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    bot_id: str = Path(..., description="Bot ID or @handle"),
    req: MarkReadRequest = ...,
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Mark incoming messages as read by message ID list."""
    updated = service.mark_as_read(session_id=chat_id, bot_id=bot_id, message_ids=req.message_ids)
    return create_success_response(data={"updated_count": updated})


@router.delete(
    "/bots/{bot_id}/inbox",
    response_model=StandardSuccessResponse,
    summary="Clear mailbox for a bot workstation",
)
def clear_inbox_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    bot_id: str = Path(..., description="Bot ID or @handle"),
    service: BotModeService = Depends(get_bot_mode_service),
) -> StandardSuccessResponse:
    """Purge all inbox and outbox messages for a bot."""
    service.clear_mailbox(session_id=chat_id, bot_id=bot_id)
    return create_success_response(data={"cleared": True})
