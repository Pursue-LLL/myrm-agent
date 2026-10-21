from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.cron.push_store import PushLevel, get_recent

router = APIRouter()


class PushMessageItem(BaseModel):
    id: str
    text: str
    level: PushLevel
    job_name: str


class PushMessagesResponse(BaseModel):
    messages: list[PushMessageItem]


@router.get("/push-messages")
async def get_push_messages() -> PushMessagesResponse:
    """Poll for recent cron push notifications (local single-user mode)."""
    messages = await get_recent(user_id="local-user")
    return PushMessagesResponse(messages=messages)
