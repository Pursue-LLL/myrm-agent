"""Chat memory extract retry API.

[INPUT]
app.services.chat.chat_service::ChatService (POS: chat metadata)
app.services.memory.retry_chat_memory_extract::schedule_retry_chat_memory_extract (POS: manual recovery)

[OUTPUT]
POST /{chat_id}/memory/retry-extract — schedule background re-extract for latest turn.

[POS]
HTTP entry for GUI manual memory extract retry. Maps service ValueError to 400/404.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.utils.errors import not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService
from app.services.memory.retry_chat_memory_extract import (
    schedule_retry_chat_memory_extract,
)

router = APIRouter()


@router.post("/{chat_id}/memory/retry-extract", response_model=StandardSuccessResponse)
async def retry_chat_memory_extract(chat_id: str) -> JSONResponse:
    """Re-run memory extraction for the latest user/assistant turn."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise not_found_error("Chat session")
    if chat.is_incognito:
        raise validation_error("Incognito chats do not support memory extraction retry")

    try:
        status = await schedule_retry_chat_memory_extract(chat_id)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise not_found_error("Chat session") from exc
        raise validation_error(message) from exc

    return success_response(data={"status": status, "chat_id": chat_id})
