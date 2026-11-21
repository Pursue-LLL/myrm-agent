"""Shared helpers for chat search tests."""

from collections.abc import Sequence
from datetime import datetime, timezone

from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchHit
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.database.repositories.conversation_recall import ConversationRecallRepository


def assert_snippet_split(hit: ConversationSearchHit, term: str) -> None:
    """The model reads the match as plain text; the UI source reference keeps its highlight."""
    assert term.lower() in hit.snippet.lower()
    assert "<mark>" not in hit.snippet
    assert hit.source_ref is not None
    assert "<mark>" in hit.source_ref.snippet


def shows_part_of(value: str, text: str, run: int = 8) -> bool:
    """Whether ``text`` holds ``run`` consecutive characters of ``value``."""
    return any(value[i : i + run] in text for i in range(len(value) - run + 1))


async def seed_chat_with_text(
    db: AsyncSession,
    chat_id: str,
    *messages: str,
    title: str = "Release notes",
    summary: str | None = None,
    is_incognito: bool = False,
    source: str = "web",
    created_at: datetime | None = None,
    sent_at: Sequence[datetime] | None = None,
) -> list[str]:
    """Insert a chat whose messages say exactly ``messages``, alternating user and assistant; returns their ids.

    ``created_at`` is when the chat row was created, by default when the test runs. ``sent_at`` is when each message was
    sent, by default a minute apart from 2026-04-17 12:01 UTC.
    """
    chat = Chat(
        id=chat_id,
        title=title,
        action_mode="agent",
        compacted_summary=summary,
        is_incognito=is_incognito,
        source=source,
    )
    if created_at is not None:
        chat.created_at = created_at
    db.add(chat)
    message_ids = [f"{chat_id}-m{number}" for number in range(1, len(messages) + 1)]
    sent_times = sent_at or [datetime(2026, 4, 17, 12, number, tzinfo=timezone.utc) for number in range(1, len(messages) + 1)]
    for number, (message_id, content, sent) in enumerate(zip(message_ids, messages, sent_times, strict=True), start=1):
        db.add(
            Message(
                id=message_id,
                chat_id=chat_id,
                role="user" if number % 2 else "assistant",
                content=content,
                sent_at=sent,
                sent_timezone="UTC",
            )
        )
    await db.commit()
    await ConversationRecallRepository.rebuild_chat(db, chat_id)
    await db.commit()
    return message_ids


async def seed_chat_and_messages(
    db: AsyncSession, *, created_at: datetime | None = None, last_sent_at: datetime | None = None
) -> str:
    """Insert a chat with several messages for search tests.

    ``created_at`` is when the chat row was created, by default when the test runs. ``last_sent_at`` is when the last
    message was sent; by default it goes out with the others.
    """
    chat_id = "chat-search-test-1"
    chat = Chat(
        id=chat_id,
        title="Docker deployment discussion",
        action_mode="agent",
    )
    if created_at is not None:
        chat.created_at = created_at
    db.add(chat)

    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
    messages_data = [
        ("msg-1", "user", "How do I deploy with Docker Compose?", now),
        ("msg-2", "assistant", "You can use docker compose up -d to deploy in detached mode.", now),
        ("msg-3", "user", "What about Kubernetes deployment?", now),
        ("msg-4", "assistant", "For Kubernetes you would use kubectl apply -f deployment.yaml", now),
        ("msg-5", "user", "Python asyncio question", last_sent_at or now),
    ]
    for msg_id, role, content, sent_at in messages_data:
        msg = Message(
            id=msg_id,
            chat_id=chat_id,
            role=role,
            content=content,
            sent_at=sent_at,
            sent_timezone="UTC",
        )
        db.add(msg)

    await db.commit()
    await ConversationRecallRepository.rebuild_chat(db, chat_id)
    await db.commit()
    return chat_id
