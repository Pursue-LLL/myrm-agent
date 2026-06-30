from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)

router = APIRouter()


class ResolvedChannelIdentityRequest(BaseModel):
    platform_user_id: str = Field(..., min_length=1)
    sandbox_owner_id: str = Field(..., min_length=1)
    channel_id: str = Field(..., min_length=1)
    channel_user_id: str = Field(..., min_length=1)
    conversation_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    thread_id: str | None = None


class ChannelIngressRequest(BaseModel):
    message_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    channel_type: str = Field(..., min_length=1)
    chat_type: str = Field(..., min_length=1)
    chat_id: str = Field(..., min_length=1)
    channel_user_id: str = Field(..., min_length=1)
    mentions_bot: bool = False
    is_reply_to_bot: bool = False
    thread_id: str | None = None
    force_new_epoch: bool = False
    timestamp: float
    resolved_identity: ResolvedChannelIdentityRequest


@router.post("/channel/message", tags=["channels"])
async def ingest_channel_message(body: ChannelIngressRequest) -> dict[str, str]:
    """Internal ingress endpoint used by Control Plane sandboxes."""
    from app.core.channel_bridge import channel_gateway

    if getattr(channel_gateway, "_router", None) is None:
        raise HTTPException(status_code=503, detail="Channel router is not available")

    is_group = body.chat_type.lower() == "group"
    msg = InboundMessage(
        channel=body.channel_type,
        sender_id=body.channel_user_id,
        content=body.content,
        sent_at=body.timestamp,
        sent_timezone="UTC",
        chat_id=body.chat_id,
        user_id=body.resolved_identity.platform_user_id,
        is_group=is_group,
        mentioned=body.mentions_bot,
        thread_id=body.resolved_identity.thread_id or body.thread_id,
        metadata={
            "resolved_identity": body.resolved_identity.model_dump(mode="json"),
            "force_new_epoch": body.force_new_epoch,
            "trusted_inbound": "control_plane",
        },
        message_id=body.message_id,
    )
    await channel_gateway.bus._handle_inbound(msg)

    return {"status": "queued"}
