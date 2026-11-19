"""Builders shared by the compaction service tests."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.models import Message


def make_messages(chat_id: str, count: int) -> list[Message]:
    """``count`` alternating user and assistant messages of a chat, oldest first."""
    now = datetime.now(UTC)
    return [
        Message(
            id=f"msg-{chat_id}-{index}",
            chat_id=chat_id,
            role="user" if index % 2 == 0 else "assistant",
            content=f"message {index}",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        )
        for index in range(count)
    ]
