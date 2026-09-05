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

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def resolve_timezone_offset_minutes(tz_str: str | None, ref_dt: datetime | None = None) -> int | None:
    """Resolve an IANA timezone string or ISO offset to minutes offset from UTC.

    Returns:
        Offset in minutes (e.g. +480 for UTC+8, -240 for UTC-4, 0 for UTC), or None if unresolved.
    """
    if not tz_str:
        return None
    cleaned = tz_str.strip()
    if not cleaned:
        return None

    if cleaned.upper() in ("Z", "UTC", "GMT"):
        return 0

    upper = cleaned.upper()
    if upper.startswith("UTC") or upper.startswith("GMT"):
        cleaned = cleaned[3:].strip()
        if not cleaned:
            return 0

    if cleaned and cleaned[0] in ("+", "-"):
        sign = 1 if cleaned[0] == "+" else -1
        rem = cleaned[1:]
        try:
            if ":" in rem:
                parts = rem.split(":", 1)
                hours = int(parts[0])
                mins = int(parts[1])
                return sign * (hours * 60 + mins)
            elif len(rem) in (3, 4):
                hours = int(rem[:-2])
                mins = int(rem[-2:])
                return sign * (hours * 60 + mins)
            else:
                hours = int(rem)
                return sign * (hours * 60)
        except (ValueError, TypeError):
            pass

    try:
        zi = ZoneInfo(cleaned)
        ref = ref_dt or datetime.now(UTC)
        offset = ref.astimezone(zi).utcoffset()
        if offset is not None:
            return int(offset.total_seconds() // 60)
    except (ZoneInfoNotFoundError, ValueError, TypeError, Exception):
        pass

    return None


def _to_utc_timestamp_ms(dt: datetime) -> int:
    """Safely convert database datetime to UTC timestamp in milliseconds.

    Protects against naive datetimes from SQLite/DB drivers being misinterpreted
    as local system timezone by Python's dt.timestamp().
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def extract_channel_message_offset_minutes(row: ChannelMessageModel) -> int | None:
    """Extract timezone offset minutes from channel message metadata if available."""
    if not row.metadata_json:
        return None
    try:
        meta = json.loads(row.metadata_json)
        if not isinstance(meta, dict):
            return None
        if "offset_minutes" in meta and isinstance(meta["offset_minutes"], (int, float)):
            return int(meta["offset_minutes"])
        if "tz_offset" in meta and isinstance(meta["tz_offset"], (int, float)):
            return int(meta["tz_offset"] // 60)
        tz_name = meta.get("timezone") or meta.get("tz")
        if isinstance(tz_name, str):
            return resolve_timezone_offset_minutes(tz_name, row.created_at)
    except Exception:
        pass
    return None


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
                ChannelMessageModel.learning_eligible.is_(True),
            )
            .order_by(desc(ChannelMessageModel.created_at))
            .limit(max_messages)
        )
        channel_res = await self._db.execute(channel_stmt)
        for row in channel_res.scalars().all():
            if row.created_at is not None:
                dt_utc = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
                if dt_utc < cutoff:
                    continue
            else:
                continue

            sender_id = row.sender_id or ""
            sender_name = row.sender_name or sender_id
            if is_alert_or_bot_sender(sender_name) or is_alert_or_bot_sender(sender_id):
                continue

            created_ms = _to_utc_timestamp_ms(row.created_at)
            is_self = bool(row.is_self)
            offset_mins = extract_channel_message_offset_minutes(row)
            results.append(
                BehavioralMessage(
                    id=f"channel:{row.id}",
                    chat_id=f"channel:{row.channel}:{row.chat_id}",
                    channel=row.channel,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    is_self=is_self,
                    created_at_ms=created_ms,
                    offset_minutes=offset_mins,
                    content=row.content or "",
                )
            )

        # 2. Fetch web/desktop internal chat messages
        chat_msg_stmt = (
            select(Message)
            .where(
                Message.is_active.is_(True),
            )
            .limit(max_messages)
        )
        chat_res = await self._db.execute(chat_msg_stmt)
        for msg in chat_res.scalars().all():
            msg_dt = msg.sent_at or msg.created_at
            if msg_dt is not None:
                # Ensure tz-aware UTC for comparison
                dt_utc = msg_dt if msg_dt.tzinfo else msg_dt.replace(tzinfo=UTC)
                if dt_utc < cutoff:
                    continue
            else:
                continue

            is_self = msg.role == "user"
            created_ms = int(dt_utc.timestamp() * 1000)
            offset_mins = resolve_timezone_offset_minutes(msg.sent_timezone, dt_utc)
            results.append(
                BehavioralMessage(
                    id=f"chat:{msg.id}",
                    chat_id=f"chat:{msg.chat_id}",
                    channel="webui",
                    sender_id="user" if is_self else "assistant",
                    sender_name="User" if is_self else "Assistant",
                    is_self=is_self,
                    created_at_ms=created_ms,
                    offset_minutes=offset_mins,
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
