"""Shared helpers for chat search tests."""

from datetime import datetime, timezone

from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.database.repositories.conversation_recall_repo import ConversationRecallRepository


async def seed_chat_and_messages(db: AsyncSession) -> str:
    """Insert a chat with several messages for search tests."""
    chat_id = "chat-search-test-1"
    chat = Chat(
        id=chat_id,
        title="Docker deployment discussion",
        action_mode="agent",
    )
    db.add(chat)

    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
    messages_data = [
        ("msg-1", "user", "How do I deploy with Docker Compose?", now),
        ("msg-2", "assistant", "You can use docker compose up -d to deploy in detached mode.", now),
        ("msg-3", "user", "What about Kubernetes deployment?", now),
        ("msg-4", "assistant", "For Kubernetes you would use kubectl apply -f deployment.yaml", now),
        ("msg-5", "user", "Python asyncio question", now),
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


class FakeConversationMemoryManager:
    def __init__(self, results: list[MemorySearchResult]) -> None:
        self._results = results

    async def search(
        self,
        query: str,
        memory_types: list[MemoryType] | None = None,
        limit: int = 5,
        include_raw: bool = False,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[MemorySearchResult]:
        return self._results[:limit]
