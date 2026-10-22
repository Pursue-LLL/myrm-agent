"""FastAPI router for Multi-Bot Mention Focus & Anti-Thrash Compaction (Item 42).

[INPUT]
- app.schemas.multi_bot_focus::{
    UpdateBotFocusRequest,
    EvaluateCompactionRequest,
    RecordCompactionRequest,
    CardHeartbeatRequest,
    PruneAbandonedStreamsRequest,
  }
- app.services.agent.multi_bot_focus_service::{
    MultiBotFocusService,
    get_multi_bot_focus_service,
  }

[OUTPUT]
- REST endpoints under /chats/{chat_id}/multi-bot for mention focus tracking,
  anti-thrash compaction decisions, and streaming card lifecycle.

[POS]
- HTTP API layer for multi-agent desktop/web focus and memory stability.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status
from myrm_agent_harness.agent.coordination.multi_bot_focus import MultiBotFocusError

from app.schemas.multi_bot_focus import (
    CardHeartbeatRequest,
    EvaluateCompactionRequest,
    PruneAbandonedStreamsRequest,
    RecordCompactionRequest,
    UpdateBotFocusRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.multi_bot_focus_service import (
    MultiBotFocusService,
    get_multi_bot_focus_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Multi-Bot Focus & Compaction"])


@router.post(
    "/chats/{chat_id}/multi-bot/focus",
    response_model=StandardSuccessResponse,
    summary="Update viewport visibility and turn freshness for a bot",
)
def update_bot_focus_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: UpdateBotFocusRequest = ...,
    service: MultiBotFocusService = Depends(get_multi_bot_focus_service),
) -> StandardSuccessResponse:
    """Update viewport presence and turn index to dynamically weigh @mention candidate."""
    try:
        snapshot = service.update_bot_focus(
            session_id=chat_id,
            bot_id=req.bot_id,
            is_viewport_active=req.is_viewport_active,
            turn_index=req.turn_index,
        )
        return create_success_response(snapshot.model_dump())
    except MultiBotFocusError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get(
    "/chats/{chat_id}/multi-bot/focus",
    response_model=StandardSuccessResponse,
    summary="Get focused bot candidate and all tracked bot snapshots",
)
def get_focused_bot_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    service: MultiBotFocusService = Depends(get_multi_bot_focus_service),
) -> StandardSuccessResponse:
    """Retrieve current highest-focus bot recommended for mention follow."""
    response = service.get_focused_bot(chat_id)
    return create_success_response(response.model_dump())


@router.post(
    "/chats/{chat_id}/multi-bot/compaction/evaluate",
    response_model=StandardSuccessResponse,
    summary="Evaluate context compaction against anti-thrash hysteresis guards",
)
def evaluate_compaction_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: EvaluateCompactionRequest = ...,
    service: MultiBotFocusService = Depends(get_multi_bot_focus_service),
) -> StandardSuccessResponse:
    """Evaluate whether context window compaction should proceed or be suppressed by anti-thrash guard."""
    try:
        result = service.evaluate_compaction(
            session_id=chat_id,
            current_tokens=req.current_tokens,
            max_context_tokens=req.max_context_tokens,
            current_turn=req.current_turn,
            policy_dto=req.policy,
        )
        return create_success_response(result.model_dump())
    except MultiBotFocusError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/chats/{chat_id}/multi-bot/compaction/record",
    response_model=StandardSuccessResponse,
    summary="Record execution of context compaction to reset cooldown",
)
def record_compaction_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: RecordCompactionRequest = ...,
    service: MultiBotFocusService = Depends(get_multi_bot_focus_service),
) -> StandardSuccessResponse:
    """Record completed compaction turn and token metrics for anti-thrash tracking."""
    service.record_compaction_executed(
        session_id=chat_id,
        executed_turn=req.executed_turn,
        tokens_after=req.tokens_after,
    )
    return create_success_response({"recorded": True, "session_id": chat_id})


@router.post(
    "/chats/{chat_id}/multi-bot/streams/heartbeat",
    response_model=StandardSuccessResponse,
    summary="Emit heartbeat for an active streaming task card",
)
def record_card_heartbeat_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: CardHeartbeatRequest = ...,
    service: MultiBotFocusService = Depends(get_multi_bot_focus_service),
) -> StandardSuccessResponse:
    """Register or refresh heartbeat timestamp for a multi-bot progress card."""
    card = service.record_card_heartbeat(
        card_id=req.card_id,
        session_id=chat_id,
        bot_id=req.bot_id,
        state=req.state,
    )
    return create_success_response(card.model_dump())


@router.post(
    "/chats/{chat_id}/multi-bot/streams/prune",
    response_model=StandardSuccessResponse,
    summary="Prune silent streaming task cards into abandoned state",
)
def prune_abandoned_streams_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: PruneAbandonedStreamsRequest = ...,
    service: MultiBotFocusService = Depends(get_multi_bot_focus_service),
) -> StandardSuccessResponse:
    """Scan and transition task cards without recent heartbeats to ABANDONED state."""
    pruned_ids = service.detect_and_prune_abandoned_streams(
        session_id=chat_id,
        timeout_seconds=req.timeout_seconds,
    )
    return create_success_response({"pruned_card_ids": pruned_ids, "count": len(pruned_ids)})


@router.post(
    "/chats/{chat_id}/multi-bot/streams/{card_id}/complete",
    response_model=StandardSuccessResponse,
    summary="Mark streaming card as cleanly completed",
)
def complete_stream_card_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    card_id: str = Path(..., min_length=1, description="Card ID"),
    service: MultiBotFocusService = Depends(get_multi_bot_focus_service),
) -> StandardSuccessResponse:
    """Mark streaming task card state as completed."""
    completed = service.mark_card_completed(card_id=card_id)
    if not completed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Card '{card_id}' not found.",
        )
    return create_success_response({"completed": True, "card_id": card_id})
