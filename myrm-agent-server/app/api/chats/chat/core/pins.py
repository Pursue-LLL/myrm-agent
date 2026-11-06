"""[OUTPUT]
- router (POS: sub-router mounted by the core package)

[POS]
Chat core API: pin / unpin and pinned-chat ordering.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService

router = APIRouter()

MAX_PINNED_CHATS = 9


class PinReorderItem(BaseModel):
    id: str
    pin_order: int = Field(..., ge=1, le=MAX_PINNED_CHATS)


class PinReorderRequest(BaseModel):
    items: list[PinReorderItem] = Field(..., min_length=1, max_length=MAX_PINNED_CHATS)


@router.patch("/{chat_id}/pin", response_model=StandardSuccessResponse)
async def pin_chat(
    chat_id: str,
) -> JSONResponse:
    """Pin a chat to the sidebar top (max 9)."""
    try:
        result = await ChatService.pin_chat(chat_id)
        return success_response(data={"isPinned": result.is_pinned, "pinOrder": result.pin_order})
    except ValueError as e:
        raise validation_error(str(e)) from e
    except LookupError as e:
        raise not_found_error("Chat session") from e
    except Exception as e:
        raise internal_error(operation="Pin chat", exception=e) from e


@router.patch("/{chat_id}/unpin", response_model=StandardSuccessResponse)
async def unpin_chat(
    chat_id: str,
) -> JSONResponse:
    """Unpin a chat from the sidebar top."""
    try:
        await ChatService.unpin_chat(chat_id)
        return success_response(data={"isPinned": False, "pinOrder": 0})
    except LookupError as e:
        raise not_found_error("Chat session") from e
    except Exception as e:
        raise internal_error(operation="Unpin chat", exception=e) from e


@router.put("/pin-reorder", response_model=StandardSuccessResponse)
async def reorder_pinned_chats(
    body: PinReorderRequest,
) -> JSONResponse:
    """Batch reorder pinned chats (after drag-and-drop)."""
    try:
        await ChatService.reorder_pinned_chats([(item.id, item.pin_order) for item in body.items])
        return success_response()
    except ValueError as e:
        raise validation_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Reorder pinned chats", exception=e) from e
