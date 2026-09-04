"""
[INPUT] channels.types::InboundMessage, ContextEntry, models.channel_message::ChannelMessageModel, logging_filter::redact_sensitive
[OUTPUT] ChannelDataPlaneService: 渠道数据平面核心服务
[POS] 渠道消息数据平面（Channel Data Plane）。负责入站消息脱敏、确定性抗噪打标、持久化明细落盘、自产回复追溯与上下文提取。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.api import (
        DistillationCandidate,
    )

from app.channels.core.logging_filter import redact_sensitive
from app.channels.types import ContextEntry, InboundMessage
from app.database.connection import get_session
from app.database.models.channel_message import ChannelMessageModel
from app.database.repositories.channel_message_repo import ChannelMessageRepository

logger = logging.getLogger(__name__)

# Keywords identifying automated monitoring or broadcast bots
_BOT_SENDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"bot\b", re.IGNORECASE),
    re.compile(r"(sentry|prometheus|grafana|alertmanager|webhook|monitor|ci[-_]?cd)", re.IGNORECASE),
    re.compile(r"(机器人|系统通知|告警|打卡|提醒助手)"),
)


def is_learning_eligible(content: str, sender_name: str | None = None) -> bool:
    """Determine whether a message represents high-signal human context suitable for memory.

    Filters out slash commands, pure noise/emojis, and automated system bot alerts.
    """
    if not content:
        return False

    stripped = content.strip()
    # Skip slash commands and control inputs
    if stripped.startswith(("/", "!", "#")):
        return False

    # Skip extremely short noise
    if len(stripped) < 2:
        return False

    # Check if sender matches bot signatures
    if sender_name:
        for pattern in _BOT_SENDER_PATTERNS:
            if pattern.search(sender_name):
                return False

    return True


class ChannelDataPlaneService:
    """Channel Data Plane service coordinating message persistence and context reconstruction."""

    @staticmethod
    async def record_inbound(
        msg: InboundMessage,
        *,
        is_trigger: bool,
    ) -> ChannelMessageModel | None:
        """Sanitize, tag, and persist an inbound message to the channel DWD ledger."""
        try:
            chat_id = msg.chat_id or msg.sender_id
            if not chat_id:
                return None

            raw_content = str(msg.content or "")
            redacted_content = redact_sensitive(raw_content)
            eligible = is_learning_eligible(redacted_content, msg.sender_name)

            message_id = msg.message_id or f"msg_{uuid.uuid4().hex[:16]}"
            meta_str = json.dumps(msg.metadata, ensure_ascii=False) if msg.metadata else None

            entry = ChannelMessageModel(
                id=message_id,
                channel=msg.channel,
                chat_id=chat_id,
                thread_id=msg.thread_id,
                sender_id=msg.sender_id or "unknown",
                sender_name=msg.sender_name,
                content=redacted_content,
                is_trigger=is_trigger,
                is_self=False,
                is_group=bool(msg.is_group),
                learning_eligible=eligible,
                metadata_json=meta_str,
                created_at=datetime.now(timezone.utc),
            )

            async with get_session() as session:
                await ChannelMessageRepository.record_message(session, entry)
                await session.commit()

            return entry
        except Exception as exc:
            # Data plane persistence must never crash the primary message dispatch pipeline
            logger.warning(
                "ChannelDataPlane: failed to persist inbound message for %s/%s: %s",
                msg.channel,
                msg.chat_id,
                exc,
            )
            return None

    @staticmethod
    async def record_outbound(
        channel: str,
        chat_id: str,
        content: str,
        *,
        thread_id: str | None = None,
        reply_to_id: str | None = None,
    ) -> ChannelMessageModel | None:
        """Persist an agent's outbound reply to prevent multi-round conversational amnesia."""
        try:
            redacted_content = redact_sensitive(content)
            message_id = f"out_{uuid.uuid4().hex[:16]}"
            meta = {"reply_to_id": reply_to_id} if reply_to_id else None

            entry = ChannelMessageModel(
                id=message_id,
                channel=channel,
                chat_id=chat_id,
                thread_id=thread_id,
                sender_id="agent",
                sender_name="Assistant",
                content=redacted_content,
                is_trigger=False,
                is_self=True,
                is_group=True,
                learning_eligible=False,
                metadata_json=json.dumps(meta) if meta else None,
                created_at=datetime.now(timezone.utc),
            )

            async with get_session() as session:
                await ChannelMessageRepository.record_message(session, entry)
                await session.commit()

            return entry
        except Exception as exc:
            logger.warning(
                "ChannelDataPlane: failed to persist outbound reply for %s/%s: %s",
                channel,
                chat_id,
                exc,
            )
            return None

    @staticmethod
    async def get_recent_context_entries(
        channel: str,
        chat_id: str,
        limit: int = 20,
    ) -> list[ContextEntry]:
        """Fetch chronological recent messages as ContextEntry instances for agent prompt injection."""
        try:
            async with get_session() as session:
                rows = await ChannelMessageRepository.get_recent_context(
                    session,
                    channel=channel,
                    chat_id=chat_id,
                    limit=limit,
                )

            entries: list[ContextEntry] = []
            for row in rows:
                entries.append(
                    ContextEntry(
                        sender_id=row.sender_id,
                        content=row.content,
                        timestamp=row.created_at.timestamp(),
                        sender_name=row.sender_name,
                    )
                )
            return entries
        except Exception as exc:
            logger.warning(
                "ChannelDataPlane: failed to load recent context for %s/%s: %s",
                channel,
                chat_id,
                exc,
            )
            return []

    @staticmethod
    def to_distillation_candidate(model: ChannelMessageModel) -> DistillationCandidate:
        """Convert a channel message model to a Harness DistillationCandidate.

        Maps channel-level properties (is_self, sender, bot signals) to the
        tri-state identity and provenance structure enforced by distillation guards.
        """
        from myrm_agent_harness.api import (
            DistillationCandidate,
            DistillationOrigin,
            EvidenceReference,
            SelfIdentityState,
            is_alert_or_bot_sender,
        )

        is_bot = not model.learning_eligible or is_alert_or_bot_sender(model.sender_name)
        is_agent = model.sender_id == "agent" or (model.is_self and model.sender_name == "Assistant")
        
        if is_agent:
            origin = DistillationOrigin.AGENT
            identity = SelfIdentityState.OTHER
        elif is_bot:
            origin = DistillationOrigin.BOT
            identity = SelfIdentityState.OTHER
        else:
            origin = DistillationOrigin.USER
            if model.is_self is True:
                identity = SelfIdentityState.SELF
            elif model.is_self is False:
                identity = SelfIdentityState.OTHER
            else:
                identity = SelfIdentityState.UNCONFIRMED

        evidence = [
            EvidenceReference(
                source_id=f"channel:{model.channel}:{model.chat_id}",
                message_id=model.id,
                channel_id=model.channel,
                timestamp=model.created_at,
                quote_snippet=model.content[:160] if model.content else None,
                author_id=model.sender_id,
            )
        ]

        return DistillationCandidate(
            content=model.content,
            origin=origin,
            is_self=identity,
            is_bot_or_alert=is_bot,
            sender_name=model.sender_name,
            evidence=evidence,
        )
