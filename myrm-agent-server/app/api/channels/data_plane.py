"""
[INPUT] database.connection::get_db, repositories.channel_message_repo::ChannelMessageRepository
[OUTPUT] data_plane_router: 渠道数据平面管理端点
[POS] 渠道数据平面监控与数据生命周期管理 API。提供环境感知消息统计、手动滚动修剪及 GDPR 遗忘权一键清空。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.repositories.channel_message_repo import ChannelMessageRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/{channel_name}/data-plane", tags=["channel-data-plane"])


class ChannelDataPlaneStatsResponse(BaseModel):
    """Aggregate statistics for a channel's inbound data plane."""

    channel: str
    total_messages: int
    learning_eligible: int
    trigger_messages: int
    ambient_messages: int
    retention_days: int = 30
    secret_scrubber_active: bool = True


class ClearDataPlaneRequest(BaseModel):
    """Request payload to clear message records for a channel or specific chat."""

    chat_id: str | None = Field(default=None, description="Optional target chat/group ID to clear")


class ClearDataPlaneResponse(BaseModel):
    channel: str
    deleted_count: int
    success: bool = True


class PruneDataPlaneRequest(BaseModel):
    retention_days: int = Field(default=30, ge=1, le=365)


class PruneDataPlaneResponse(BaseModel):
    channel: str
    pruned_count: int
    success: bool = True


@router.get("", response_model=ChannelDataPlaneStatsResponse)
async def get_channel_data_plane_stats(
    channel_name: str,
    db: AsyncSession = Depends(get_db),
) -> ChannelDataPlaneStatsResponse:
    """Fetch inbound message ledger metrics for the specified channel."""
    stats = await ChannelMessageRepository.get_channel_stats(db, channel=channel_name)
    total = stats.get("total_messages", 0)
    trigger = stats.get("trigger_messages", 0)
    learning = stats.get("learning_eligible", 0)
    ambient = max(0, total - trigger)

    return ChannelDataPlaneStatsResponse(
        channel=channel_name,
        total_messages=total,
        learning_eligible=learning,
        trigger_messages=trigger,
        ambient_messages=ambient,
        retention_days=30,
        secret_scrubber_active=True,
    )


@router.post("/clear", response_model=ClearDataPlaneResponse)
async def clear_channel_data_plane(
    channel_name: str,
    payload: ClearDataPlaneRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ClearDataPlaneResponse:
    """GDPR Right to be Forgotten: clear cached message records for the channel or specific chat."""
    chat_id = payload.chat_id if payload else None
    deleted = await ChannelMessageRepository.clear_chat_history(db, channel=channel_name, chat_id=chat_id)
    await db.commit()
    logger.info("ChannelDataPlane: cleared %d messages for %s (chat_id=%s)", deleted, channel_name, chat_id)

    return ClearDataPlaneResponse(
        channel=channel_name,
        deleted_count=deleted,
        success=True,
    )


@router.post("/prune", response_model=PruneDataPlaneResponse)
async def prune_channel_data_plane(
    channel_name: str,
    payload: PruneDataPlaneRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> PruneDataPlaneResponse:
    """Trigger lifecycle pruning of records older than retention_days."""
    days = payload.retention_days if payload else 30
    pruned = await ChannelMessageRepository.prune_expired(db, retention_days=days)
    await db.commit()
    logger.info("ChannelDataPlane: pruned %d expired messages (retention=%d days)", pruned, days)

    return PruneDataPlaneResponse(
        channel=channel_name,
        pruned_count=pruned,
        success=True,
    )
