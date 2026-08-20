"""ensure_chat_source recall sync affects FTS ranking integration tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from myrm_agent_harness.toolkits.memory.conversation_search.types import (
    ConversationSearchRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.database.repositories.conversation_recall import ConversationRecallRepository
from app.services.chat.chat_crud import _ChatCrudMixin
from app.services.chat.conversation_search_service import ConversationSearchService


@pytest.mark.asyncio
async def test_ensure_chat_source_sync_demotes_in_search_without_rebuild(
    fts_db: AsyncSession,
) -> None:
    """Cron tagging must sync recall index so interactive sessions outrank automation."""
    web_id = "chat-rank-web-sync"
    cron_id = "chat-rank-cron-sync"
    now = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
    fts_db.add_all(
        [
            Chat(id=web_id, title="Alpha planning web", action_mode="agent", source="web"),
            Chat(id=cron_id, title="Alpha digest cron", action_mode="agent", source="web"),
        ]
    )
    fts_db.add_all(
        [
            Message(
                id="msg-web-sync-alpha",
                chat_id=web_id,
                role="assistant",
                content="Alpha project planning notes from interactive chat.",
                sent_at=now,
                sent_timezone="UTC",
            ),
            Message(
                id="msg-cron-sync-alpha",
                chat_id=cron_id,
                role="assistant",
                content="Alpha project cron summary for nightly automation.",
                sent_at=now,
                sent_timezone="UTC",
            ),
        ]
    )
    await fts_db.commit()
    await ConversationRecallRepository.rebuild_chat(fts_db, web_id)
    await ConversationRecallRepository.rebuild_chat(fts_db, cron_id)
    await fts_db.commit()

    await _ChatCrudMixin.ensure_chat_source(cron_id, "cron")

    response = await ConversationSearchService.search(
        ConversationSearchRequest(query="alpha project", limit=3),
        agent_id=None,
        memory_manager=None,
    )

    assert len(response.hits) >= 2
    assert response.hits[0].conversation_id == web_id
    assert response.hits[0].score >= response.hits[1].score
