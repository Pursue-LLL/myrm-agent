"""Extension UI Interaction and Reverse Push Handshake API Routes.

[INPUT]
- fastapi from fastapi
- pydantic from pydantic
- UIResponse from myrm_agent_harness.agent.ui
- get_ui_request_manager from app.services.ui_interaction
- success_response from app.core.utils.response_utils

[OUTPUT]
- router (APIRouter) exposing /ui-requests, /ui-response/{request_id}, /ui-cancel/{request_id}

[POS]
API routes handling bi-directional Extension UI interaction handshake between frontend clients and running agent instances (Item 28).
File length < 180 lines. Zero `Any`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.ui import UIResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.services.ui_interaction import get_ui_request_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class UIResponsePayload(BaseModel):
    """Payload sent by client to resolve an interactive UI prompt."""

    value: str | bool | None = Field(default=None, description="Chosen value, boolean confirmation, or input string")
    cancelled: bool = Field(default=False, description="Whether the operator explicitly dismissed/cancelled the prompt")
    error: str | None = Field(default=None, description="Optional error message from client UI")


class UICancelPayload(BaseModel):
    """Payload to cancel an interactive prompt."""

    reason: str = Field(default="Interaction cancelled by operator", description="Reason for cancellation")


@router.get("/{chat_id}/ui-requests", response_class=JSONResponse)
async def get_pending_ui_requests(chat_id: str) -> JSONResponse:
    """Lists all active interactive UI prompts awaiting user response for the specified chat."""
    manager = get_ui_request_manager()
    requests = await manager.get_pending_requests(chat_id)
    serialized = [req.to_dict() for req in requests]
    return success_response(
        data={"requests": serialized, "count": len(serialized)},
    )


@router.post("/{chat_id}/ui-response/{request_id}", response_class=JSONResponse)
async def submit_ui_response(
    chat_id: str,
    request_id: str,
    payload: UIResponsePayload,
) -> JSONResponse:
    """Submits operator response to a pending interactive UI request, unblocking the agent execution thread."""
    manager = get_ui_request_manager()
    ui_resp = UIResponse(
        request_id=request_id,
        value=payload.value,
        cancelled=payload.cancelled,
        error=payload.error,
    )

    resolved = await manager.resolve_response(chat_id, ui_resp)
    if not resolved:
        logger.warning(
            "[submit_ui_response] Request %s in chat %s not found or already completed",
            request_id,
            chat_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"UI request '{request_id}' not found or already completed",
        )

    logger.info(
        "[submit_ui_response] Successfully resolved UI request %s for chat %s",
        request_id,
        chat_id,
    )
    return success_response(
        data={"resolved": True, "request_id": request_id},
    )


@router.post("/{chat_id}/ui-cancel/{request_id}", response_class=JSONResponse)
async def cancel_ui_request(
    chat_id: str,
    request_id: str,
    payload: UICancelPayload | None = None,
) -> JSONResponse:
    """Cancels a pending interactive UI request."""
    manager = get_ui_request_manager()
    reason = payload.reason if payload is not None else "Interaction cancelled by operator"
    cancelled = await manager.cancel_request(chat_id, request_id, reason=reason)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"UI request '{request_id}' not found or already completed",
        )

    return success_response(
        data={"cancelled": True, "request_id": request_id},
    )
