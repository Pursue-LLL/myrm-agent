"""Chat and reply rows seeded under a channel session key, shared by the tests of the channel key lookups."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chat import Chat, Message


async def seed_channel_chat(db: AsyncSession, key: str, *, idle_minutes: float = 0.0) -> str:
    """Store a chat under ``key`` whose last activity was ``idle_minutes`` ago; return its id."""
    now = datetime.now(UTC)
    chat_id = f"chat-{uuid.uuid4().hex[:8]}"
    db.add(
        Chat(
            id=chat_id,
            source="telegram",
            channel_session_key=key,
            created_at=now,
            updated_at=now - timedelta(minutes=idle_minutes),
        )
    )
    await db.commit()
    return chat_id


async def seed_costed_reply(db: AsyncSession, chat_id: str, cost_usd: float, *, sender_id: str = "u1") -> None:
    """Store an assistant reply of ``chat_id`` that cost ``cost_usd`` and answered ``sender_id``.

    The budget day is the local calendar day, so the reply is stamped in local time.
    """
    now = datetime.now()  # noqa: DTZ005
    db.add(
        Message(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            chat_id=chat_id,
            role="assistant",
            content="ok",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
            extra_data={"costUsd": cost_usd, "channelSenderId": sender_id},
        )
    )
    await db.commit()
