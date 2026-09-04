"""Evidence playback and provenance inspection service.

[INPUT]
app.database.models.channel_message::ChannelMessageModel (POS: 渠道消息 DWD 表)
app.database.models.chat::Message (POS: 会话消息表)
app.channels.core.logging_filter::redact_sensitive (POS: 敏感凭据过滤脱敏)
app.schemas.memory.command_center::(MemoryEvidencePlaybackResponse, MemoryEvidencePlaybackTurn)

[OUTPUT]
EvidencePlaybackService: 记忆证据链溯源、上下文切片回放与敏感凭据脱敏服务

[POS]
Server 业务服务层。桥接底层对话流水表与 Memory Command Center 证据抽屉，
根据 message_id / source_id 穿透提取前后交互对话切片，保证 0 LLM 调用与隐私安全。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.core.logging_filter import redact_sensitive
from app.database.models.channel_message import ChannelMessageModel
from app.database.models.chat import Message
from app.schemas.memory.command_center import (
    MemoryEvidencePlaybackResponse,
    MemoryEvidencePlaybackTurn,
)

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_HALF_WINDOW: Final[int] = 2


class EvidencePlaybackService:
    """Service retrieving conversation slices anchoring memory facts with credential sanitization."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_playback(
        self,
        source_id: str | None = None,
        message_id: str | None = None,
        channel_id: str | None = None,
        quote_snippet: str | None = None,
        author_id: str | None = None,
        author_name: str | None = None,
        occurred_at: datetime | None = None,
        is_user_locked: bool = False,
        half_window: int = DEFAULT_CONTEXT_HALF_WINDOW,
    ) -> MemoryEvidencePlaybackResponse:
        """Resolve evidence playback.

        Attempts Web chat message table first; then falls back to channel_messages table;
        if neither exists (e.g. purged or archived), returns graceful archived snapshot.
        """
        # 1. Try resolving via Web Chat `Message` table if message_id or source_id provided
        if message_id or source_id:
            chat_slice = await self._resolve_chat_message_slice(
                message_id=message_id,
                chat_id=source_id,
                half_window=half_window,
            )
            if chat_slice is not None:
                chat_slice.quote_snippet = quote_snippet
                chat_slice.author_id = author_id
                chat_slice.author_name = author_name
                chat_slice.is_user_locked = is_user_locked
                return chat_slice

        # 2. Try resolving via Channel DWD `ChannelMessageModel`
        if message_id or channel_id or source_id:
            channel_slice = await self._resolve_channel_message_slice(
                message_id=message_id,
                channel_or_chat_id=channel_id or source_id,
                half_window=half_window,
            )
            if channel_slice is not None:
                channel_slice.quote_snippet = quote_snippet
                channel_slice.author_id = author_id
                channel_slice.author_name = author_name
                channel_slice.is_user_locked = is_user_locked
                return channel_slice

        # 3. Graceful fallback: return archived snapshot with self-contained quote
        if quote_snippet:
            return MemoryEvidencePlaybackResponse(
                status="archived_snapshot",
                source_type="chat" if source_id else "unknown",
                source_id=source_id,
                target_message_id=message_id,
                channel=channel_id,
                quote_snippet=redact_sensitive(quote_snippet),
                author_name=author_name,
                author_id=author_id,
                occurred_at=occurred_at or datetime.now(UTC),
                turns=[
                    MemoryEvidencePlaybackTurn(
                        message_id=message_id or "archived-ref",
                        role="user",
                        sender_name=author_name or "User",
                        content=redact_sensitive(quote_snippet),
                        sent_at=occurred_at or datetime.now(UTC),
                        is_target=True,
                        is_self=True,
                    )
                ],
                is_user_locked=is_user_locked,
            )

        return MemoryEvidencePlaybackResponse(
            status="not_found",
            source_id=source_id,
            target_message_id=message_id,
            channel=channel_id,
            quote_snippet=None,
            is_user_locked=is_user_locked,
        )

    async def _resolve_chat_message_slice(
        self,
        message_id: str | None,
        chat_id: str | None,
        half_window: int,
    ) -> MemoryEvidencePlaybackResponse | None:
        """Fetch target chat message and surrounding conversation turns."""
        target_msg: Message | None = None
        if message_id:
            target_msg = await self._db.get(Message, message_id)

        if target_msg is None and chat_id and message_id:
            # Query by chat_id and message_id
            stmt = select(Message).where(Message.chat_id == chat_id, Message.id == message_id)
            target_msg = (await self._db.execute(stmt)).scalar_one_or_none()

        if target_msg is None:
            return None

        actual_chat_id = target_msg.chat_id

        # Query surrounding turns ordered by sent_at
        # 1. Prior messages
        prior_stmt = (
            select(Message)
            .where(Message.chat_id == actual_chat_id, Message.sent_at < target_msg.sent_at)
            .order_by(desc(Message.sent_at))
            .limit(half_window)
        )
        prior_messages = list((await self._db.execute(prior_stmt)).scalars().all())
        prior_messages.reverse()

        # 2. Subsequent messages
        subsequent_stmt = (
            select(Message)
            .where(Message.chat_id == actual_chat_id, Message.sent_at > target_msg.sent_at)
            .order_by(Message.sent_at)
            .limit(half_window)
        )
        subsequent_messages = list((await self._db.execute(subsequent_stmt)).scalars().all())

        all_records = prior_messages + [target_msg] + subsequent_messages
        turns: list[MemoryEvidencePlaybackTurn] = []

        for rec in all_records:
            is_target = rec.id == target_msg.id
            turns.append(
                MemoryEvidencePlaybackTurn(
                    message_id=rec.id,
                    role=rec.role,
                    sender_name=None if rec.role == "assistant" else "User",
                    content=redact_sensitive(rec.content),
                    sent_at=rec.sent_at,
                    is_target=is_target,
                    is_self=rec.role == "user",
                )
            )

        return MemoryEvidencePlaybackResponse(
            status="live_context",
            source_type="chat",
            source_id=actual_chat_id,
            target_message_id=target_msg.id,
            occurred_at=target_msg.sent_at,
            turns=turns,
        )

    async def _resolve_channel_message_slice(
        self,
        message_id: str | None,
        channel_or_chat_id: str | None,
        half_window: int,
    ) -> MemoryEvidencePlaybackResponse | None:
        """Fetch target channel message and surrounding conversation turns."""
        target_msg: ChannelMessageModel | None = None
        if message_id:
            target_msg = await self._db.get(ChannelMessageModel, message_id)

        if target_msg is None and channel_or_chat_id and message_id:
            stmt = select(ChannelMessageModel).where(
                ChannelMessageModel.chat_id == channel_or_chat_id,
                ChannelMessageModel.id == message_id,
            )
            target_msg = (await self._db.execute(stmt)).scalar_one_or_none()

        if target_msg is None:
            return None

        actual_chat_id = target_msg.chat_id
        actual_channel = target_msg.channel

        # Prior messages in this channel/chat
        prior_stmt = (
            select(ChannelMessageModel)
            .where(
                ChannelMessageModel.chat_id == actual_chat_id,
                ChannelMessageModel.created_at < target_msg.created_at,
            )
            .order_by(desc(ChannelMessageModel.created_at))
            .limit(half_window)
        )
        prior_messages = list((await self._db.execute(prior_stmt)).scalars().all())
        prior_messages.reverse()

        # Subsequent messages
        subsequent_stmt = (
            select(ChannelMessageModel)
            .where(
                ChannelMessageModel.chat_id == actual_chat_id,
                ChannelMessageModel.created_at > target_msg.created_at,
            )
            .order_by(ChannelMessageModel.created_at)
            .limit(half_window)
        )
        subsequent_messages = list((await self._db.execute(subsequent_stmt)).scalars().all())

        all_records = prior_messages + [target_msg] + subsequent_messages
        turns: list[MemoryEvidencePlaybackTurn] = []

        for rec in all_records:
            is_target = rec.id == target_msg.id
            turns.append(
                MemoryEvidencePlaybackTurn(
                    message_id=rec.id,
                    role="user" if (rec.is_self or rec.is_self is None) else "collaborator",
                    sender_name=rec.sender_name or rec.sender_id,
                    content=redact_sensitive(rec.content),
                    sent_at=rec.created_at,
                    is_target=is_target,
                    is_self=rec.is_self,
                )
            )

        return MemoryEvidencePlaybackResponse(
            status="live_context",
            source_type="channel",
            source_id=actual_chat_id,
            target_message_id=target_msg.id,
            channel=actual_channel,
            occurred_at=target_msg.created_at,
            turns=turns,
        )
