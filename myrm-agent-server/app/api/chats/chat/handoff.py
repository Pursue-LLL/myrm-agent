"""Cross-platform session handoff endpoint.

[INPUT]
- services.chat.handoff::handoff_chat (POS: handoff business logic)

[OUTPUT]
- POST /{chat_id}/handoff: transfer a conversation to another channel

[POS]
Web→Channel handoff API. Enables the frontend to migrate an active
conversation to an IM channel (Telegram, WeChat, Feishu, etc.).
"""

from __future__ import annotations

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import not_found_error, validation_error
from app.core.utils.response_utils import success_response

router = APIRouter()


class HandoffRequest(BaseModel):
    target_channel: str = Field(..., min_length=1, description="Target channel name (e.g. telegram_abc123)")


@router.post("/{chat_id}/handoff")
async def handoff_session(
    body: HandoffRequest,
    chat_id: str = Path(..., description="Chat session ID"),
) -> JSONResponse:
    """Transfer a chat session to a different channel/platform."""
    from app.services.chat.handoff import handoff_chat

    result = await handoff_chat(chat_id, body.target_channel)

    if not result.success:
        if "not found" in result.error.lower():
            raise not_found_error(result.error)
        raise validation_error(result.error)

    return success_response(
        {
            "targetChannel": result.target_channel,
            "targetSessionKey": result.target_session_key,
        }
    )
