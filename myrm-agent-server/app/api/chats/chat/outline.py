"""Chat Turn Outline API — Extract and serve lightweight session turn projection.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException
- app.services.chat.chat_service::ChatService
- app.database.connection::get_db

[OUTPUT]
- router: Mounted under /chats/{chat_id}/outline
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.services.chat.chat_service import ChatService

router = APIRouter()


class TurnOutlineItem(BaseModel):
    turn_index: int
    user_message_id: str
    assistant_message_id: str | None = None
    prompt_preview: str = ""
    reply_preview: str | None = None
    created_at: str | None = None
    message_count: int = Field(default=1)


@router.get("/{chat_id}/outline", response_model=list[TurnOutlineItem])
async def get_chat_outline(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[TurnOutlineItem]:
    """Retrieve lightweight turn-level projection outline for quick navigation."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat session not found")

    raw_turns = await ChatService.get_chat_turn_outline(chat_id)
    return [TurnOutlineItem.model_validate(item) for item in raw_turns]
