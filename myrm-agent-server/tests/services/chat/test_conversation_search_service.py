"""ConversationSearchService tests."""

from datetime import datetime, timezone

import pytest
from myrm_agent_harness.toolkits.memory.conversation_search import ConversationSearchRequest
from myrm_agent_harness.toolkits.memory.types import ConversationMemory, MemorySearchResult, MemoryType
from pydantic import ValidationError
from search_support import FakeConversationMemoryManager, seed_chat_and_messages
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, ConversationFork, Message
from app.database.repositories.conversation_recall import ConversationRecallRepository
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService
from app.services.chat.conversation_search_service import ConversationSearchService


class TestConversationSearchService:
    @pytest.mark.asyncio
    async def test_search_returns_conversation_summary_and_snippet(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        await fts_db.execute(
            text("UPDATE chats SET compacted_summary = :summary, agent_id = :agent_id WHERE id = :chat_id"),
            {
                "summary": "Deployment summary: use Docker Compose locally before Kubernetes.",
                "agent_id": "agent-a",
                "chat_id": chat_id,
            },
        )
        await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3, current_conversation_id=None),
            agent_id="agent-a",
            memory_manager=None,
        )

        assert response.mode == "search"
        assert len(response.hits) == 1
        assert response.hits[0].conversation_id == chat_id
        assert response.hits[0].summary == "Deployment summary: use Docker Compose locally before Kubernetes."
        assert "<mark>" in response.hits[0].snippet

    @pytest.mark.asyncio
    async def test_search_returns_matching_segment_message_id(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="Kubernetes", limit=3, current_conversation_id=None),
            agent_id=None,
            memory_manager=None,
        )

        assert response.hits
        assert response.hits[0].conversation_id == chat_id
        assert response.hits[0].message_id in {"msg-3", "msg-4"}
        assert "<mark>" in response.hits[0].snippet

    @pytest.mark.asyncio
    async def test_empty_query_returns_recent_conversations(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="", limit=3, current_conversation_id=None),
            agent_id=None,
            memory_manager=None,
        )

        assert response.mode == "recent"
        assert [hit.conversation_id for hit in response.hits] == [chat_id]

    @pytest.mark.asyncio
    async def test_current_conversation_is_excluded(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3, current_conversation_id=chat_id),
            agent_id=None,
            memory_manager=None,
        )

        assert response.hits == []

    @pytest.mark.asyncio
    async def test_current_agent_scope_is_hard_filter(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        await fts_db.execute(text("UPDATE chats SET agent_id = 'agent-a' WHERE id = :chat_id"), {"chat_id": chat_id})
        await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3, scope="current_agent"),
            agent_id="agent-b",
            memory_manager=None,
        )

        assert response.hits == []

    @pytest.mark.asyncio
    async def test_current_agent_scope_filters_null_agent(self, fts_db: AsyncSession):
        null_agent_chat_id = await seed_chat_and_messages(fts_db)
        other_chat_id = "chat-agent-b"
        fts_db.add(Chat(id=other_chat_id, title="Other agent Docker notes", action_mode="agent", agent_id="agent-b"))
        fts_db.add(
            Message(
                id="msg-agent-b",
                chat_id=other_chat_id,
                role="user",
                content="Docker guidance from a different agent",
                sent_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
                sent_timezone="UTC",
            )
        )
        await fts_db.commit()
        await ConversationRecallRepository.rebuild_chat(fts_db, other_chat_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3, scope="current_agent"),
            agent_id=None,
            memory_manager=None,
        )

        assert [hit.conversation_id for hit in response.hits] == [null_agent_chat_id]

    def test_all_scope_is_rejected_by_contract(self):
        with pytest.raises(ValidationError):
            ConversationSearchRequest(query="docker", limit=3, scope="all")

    @pytest.mark.asyncio
    async def test_search_can_match_precomputed_summary_only(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        await fts_db.execute(
            text("UPDATE chats SET compacted_summary = :summary WHERE id = :chat_id"),
            {
                "summary": "Strategic recall keyword: bluegreenphoenix cutover plan.",
                "chat_id": chat_id,
            },
        )
        await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="bluegreenphoenix", limit=3),
            agent_id=None,
            memory_manager=None,
        )

        assert [hit.conversation_id for hit in response.hits] == [chat_id]
        assert response.hits[0].summary == "Strategic recall keyword: bluegreenphoenix cutover plan."
        assert "<mark>" in response.hits[0].snippet

    @pytest.mark.asyncio
    async def test_search_uses_or_fallback_for_broad_natural_language_query(self, fts_db: AsyncSession):
        chat_id = "chat-bluegreen"
        fts_db.add(Chat(id=chat_id, title="Bluegreen release notes", action_mode="agent"))
        fts_db.add(
            Message(
                id="msg-bluegreen",
                chat_id=chat_id,
                role="assistant",
                content="Bluegreen rollout should verify health checks before traffic shift.",
                sent_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
                sent_timezone="UTC",
            )
        )
        await fts_db.commit()
        await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="bluegreen canary approval", limit=3),
            agent_id=None,
            memory_manager=None,
        )

        assert [hit.conversation_id for hit in response.hits] == [chat_id]
        assert "Bluegreen" in response.hits[0].snippet

    @pytest.mark.asyncio
    async def test_semantic_hit_is_hydrated_from_recall_index(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        manager = FakeConversationMemoryManager(
            [
                MemorySearchResult(
                    memory=ConversationMemory(
                        id="mem-docker",
                        content="Semantic deployment summary",
                        raw_exchange="",
                        source_chat_id=chat_id,
                        source_message_id="msg-1",
                    ),
                    score=0.92,
                    memory_type=MemoryType.CONVERSATION,
                )
            ]
        )

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="semantic-only", limit=3),
            agent_id=None,
            memory_manager=manager,
        )

        assert [hit.conversation_id for hit in response.hits] == [chat_id]
        assert response.hits[0].message_id == "msg-1"
        assert "Docker Compose" in response.hits[0].snippet
        assert response.hits[0].source_ref is not None
        assert "Docker Compose" in response.hits[0].source_ref.snippet

    @pytest.mark.asyncio
    async def test_semantic_search_respects_excluded_conversation(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        await ConversationRecallRepository.set_excluded(fts_db, chat_id, True)
        await fts_db.commit()
        manager = FakeConversationMemoryManager(
            [
                MemorySearchResult(
                    memory=ConversationMemory(
                        id="mem-excluded",
                        content="Excluded deployment summary",
                        raw_exchange="Excluded raw text should not leak.",
                        source_chat_id=chat_id,
                        source_message_id="msg-1",
                    ),
                    score=0.98,
                    memory_type=MemoryType.CONVERSATION,
                )
            ]
        )

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="semantic-only", limit=3),
            agent_id=None,
            memory_manager=manager,
        )

        assert response.hits == []

    @pytest.mark.asyncio
    async def test_semantic_search_uses_server_agent_scope(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        await fts_db.execute(text("UPDATE chats SET agent_id = 'agent-a' WHERE id = :chat_id"), {"chat_id": chat_id})
        await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()
        manager = FakeConversationMemoryManager(
            [
                MemorySearchResult(
                    memory=ConversationMemory(
                        id="mem-agent-a",
                        content="Agent scoped summary",
                        raw_exchange="",
                        source_chat_id=chat_id,
                        source_message_id="msg-1",
                    ),
                    score=0.91,
                    memory_type=MemoryType.CONVERSATION,
                )
            ]
        )

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="semantic-only", limit=3, scope="current_agent"),
            agent_id="agent-b",
            memory_manager=manager,
        )

        assert response.hits == []

    @pytest.mark.asyncio
    async def test_semantic_search_respects_lineage(self, fts_db: AsyncSession):
        parent_id = "chat-parent"
        current_id = "chat-current"
        unrelated_id = "chat-unrelated"
        fts_db.add_all(
            [
                Chat(id=parent_id, title="Parent chat", action_mode="agent"),
                Chat(id=current_id, title="Current chat", action_mode="agent"),
                Chat(id=unrelated_id, title="Unrelated chat", action_mode="agent"),
                ConversationFork(child_chat_id=current_id, parent_chat_id=parent_id, fork_message_index=0),
            ]
        )
        now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
        fts_db.add_all(
            [
                Message(
                    id="msg-parent",
                    chat_id=parent_id,
                    role="assistant",
                    content="Parent chat discussed Docker deployment.",
                    sent_at=now,
                    sent_timezone="UTC",
                ),
                Message(
                    id="msg-unrelated",
                    chat_id=unrelated_id,
                    role="assistant",
                    content="Unrelated chat discussed Docker deployment.",
                    sent_at=now,
                    sent_timezone="UTC",
                ),
            ]
        )
        await fts_db.commit()
        await ConversationRecallRepository.rebuild_chat(fts_db, parent_id)
        await ConversationRecallRepository.rebuild_chat(fts_db, unrelated_id)
        await fts_db.commit()

        manager = FakeConversationMemoryManager(
            [
                MemorySearchResult(
                    memory=ConversationMemory(
                        id="mem-parent",
                        content="Parent deployment summary",
                        raw_exchange="Parent chat discussed Docker deployment.",
                        source_chat_id=parent_id,
                    ),
                    score=0.9,
                    memory_type=MemoryType.CONVERSATION,
                ),
                MemorySearchResult(
                    memory=ConversationMemory(
                        id="mem-unrelated",
                        content="Unrelated deployment summary",
                        raw_exchange="Unrelated chat discussed Docker deployment.",
                        source_chat_id=unrelated_id,
                    ),
                    score=0.95,
                    memory_type=MemoryType.CONVERSATION,
                ),
            ]
        )

        response = await ConversationSearchService.search(
            ConversationSearchRequest(
                query="docker",
                limit=3,
                current_conversation_id=current_id,
                lineage="ancestors",
            ),
            agent_id=None,
            memory_manager=manager,
        )

        assert [hit.conversation_id for hit in response.hits] == [parent_id]

    @pytest.mark.asyncio
    async def test_excluded_conversation_is_not_recalled(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        await ConversationRecallRepository.set_excluded(fts_db, chat_id, True)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3),
            agent_id=None,
            memory_manager=None,
        )

        assert response.hits == []

    @pytest.mark.asyncio
    async def test_excluded_conversation_can_be_listed_and_restored(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        assert await ConversationRecallIndexService.set_chat_excluded(chat_id, True) is True

        excluded_rows, total = await ConversationRecallIndexService.list_documents(excluded=True, page=1, page_size=10)
        assert total == 1
        assert [row.chat_id for row in excluded_rows] == [chat_id]

        assert await ConversationRecallIndexService.set_chat_excluded(chat_id, False) is True
        excluded_rows, total = await ConversationRecallIndexService.list_documents(excluded=True, page=1, page_size=10)
        assert total == 0
        assert excluded_rows == []
