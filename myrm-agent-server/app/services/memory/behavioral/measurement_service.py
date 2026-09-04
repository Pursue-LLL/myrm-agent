"""Behavioral measurement service.

[INPUT]
app.database.models.channel_message::ChannelMessageModel (POS: 渠道消息 DWD 表)
app.database.models.chat::Message (POS: 会话消息表)
myrm_agent_harness.toolkits.memory::MemoryManager (POS: 内存管理器)
myrm_agent_harness.api::(BehavioralMessage, BehavioralStatsOptions, RoutineMeasurement, compute_routine_measurement, generate_behavioral_profile_candidates, is_alert_or_bot_sender)

[OUTPUT]
BehavioralMeasurementService: 行为特征提取、滑动窗口切片测量与画像沉淀服务

[POS]
Server 业务服务层。桥接底层消息明细流水表与 Harness 确定性行为特征算子，
将高置信度行为特征持久化至 Profile 记忆事实，并提供前端 Command Center 结构化 DTO。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Final

from myrm_agent_harness.api import (
    BehavioralMessage,
    BehavioralStatsOptions,
    RoutineMeasurement,
    compute_routine_measurement,
    generate_behavioral_profile_candidates,
    is_alert_or_bot_sender,
)
from myrm_agent_harness.toolkits.memory import MemoryManager
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel_message import ChannelMessageModel
from app.database.models.chat import Message

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS: Final[int] = 30
MAX_WINDOW_MESSAGES: Final[int] = 5000


class BehavioralMeasurementService:
    """Orchestrates deterministic behavioral feature extraction and profile synchronization."""

    def __init__(self, db: AsyncSession, manager: MemoryManager) -> None:
        self._db = db
        self._manager = manager

    async def collect_behavioral_messages(
        self,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        max_messages: int = MAX_WINDOW_MESSAGES,
    ) -> list[BehavioralMessage]:
        """Collect normalized messages across channels and internal chats within sliding window.

        Applies distillation guards to discard automated bots and alert webhook messages.
        """
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        results: list[BehavioralMessage] = []

        # 1. Fetch channel messages (external chat planes: Slack, Feishu, Webhook, etc.)
        channel_stmt = (
            select(ChannelMessageModel)
            .where(
                ChannelMessageModel.created_at >= cutoff,
                ChannelMessageModel.learning_eligible.is_(True),
            )
            .order_by(desc(ChannelMessageModel.created_at))
            .limit(max_messages)
        )
        channel_res = await self._db.execute(channel_stmt)
        for row in channel_res.scalars().all():
            sender_id = row.sender_id or ""
            sender_name = row.sender_name or sender_id
            if is_alert_or_bot_sender(sender_name) or is_alert_or_bot_sender(sender_id):
                continue

            created_ms = int(row.created_at.timestamp() * 1000)
            is_self = bool(row.is_self)
            results.append(
                BehavioralMessage(
                    id=f"channel:{row.id}",
                    chat_id=f"channel:{row.channel}:{row.chat_id}",
                    channel=row.channel,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    is_self=is_self,
                    created_at_ms=created_ms,
                    content=row.content or "",
                )
            )

        # 2. Fetch web/desktop internal chat messages
        chat_msg_stmt = (
            select(Message)
            .where(
                Message.created_at >= cutoff,
                Message.is_active.is_(True),
            )
            .order_by(desc(Message.created_at))
            .limit(max_messages)
        )
        chat_res = await self._db.execute(chat_msg_stmt)
        for msg in chat_res.scalars().all():
            is_self = msg.role == "user"
            created_ms = int(msg.created_at.timestamp() * 1000)
            results.append(
                BehavioralMessage(
                    id=f"chat:{msg.id}",
                    chat_id=f"chat:{msg.chat_id}",
                    channel="webui",
                    sender_id="user" if is_self else "assistant",
                    sender_name="User" if is_self else "Assistant",
                    is_self=is_self,
                    created_at_ms=created_ms,
                    content=msg.content or "",
                )
            )

        results.sort(key=lambda m: m.created_at_ms)
        return results

    async def measure(
        self,
        options: BehavioralStatsOptions | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> RoutineMeasurement:
        """Compute current deterministic behavioral metrics without side effects."""
        opts = options or BehavioralStatsOptions()
        messages = await self.collect_behavioral_messages(lookback_days=lookback_days)
        return compute_routine_measurement(messages, opts)

    async def sync_profile_attributes(
        self,
        options: BehavioralStatsOptions | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> list[str]:
        """Measure routines and persist qualified candidates into Profile memories.

        Returns the list of updated profile keys.
        """
        opts = options or BehavioralStatsOptions()
        messages = await self.collect_behavioral_messages(lookback_days=lookback_days)
        candidates = generate_behavioral_profile_candidates(messages, opts)

        updated_keys: list[str] = []
        for cand in candidates:
            if not cand.profile_key or not cand.profile_value:
                continue

            try:
                await self._manager.set_system_profile_attribute(
                    key=cand.profile_key,
                    value=cand.profile_value,
                )
                updated_keys.append(cand.profile_key)
            except Exception as e:
                logger.warning(
                    "Failed to persist behavioral profile %s: %s", cand.profile_key, e
                )

        return updated_keys
