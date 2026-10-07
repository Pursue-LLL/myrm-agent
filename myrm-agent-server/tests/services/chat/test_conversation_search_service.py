"""ConversationSearchService tests."""

from datetime import datetime, timezone

import pytest
from myrm_agent_harness.toolkits.memory.conversation_search import (
    ConversationSearchRequest,
)
from pydantic import ValidationError
from search_support import seed_chat_and_messages
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, ConversationFork, Message
from app.database.repositories.conversation_recall import ConversationRecallRepository
from app.services.chat.conversation_recall_index_service import (
    ConversationRecallIndexService,
)
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
        )

        assert response.mode == "recent"
        assert [hit.conversation_id for hit in response.hits] == [chat_id]

    @pytest.mark.asyncio
    async def test_current_conversation_is_excluded(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3, current_conversation_id=chat_id),
            agent_id=None,
        )

        assert response.hits == []

    @pytest.mark.asyncio
    async def test_current_agent_scope_is_hard_filter(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        await fts_db.execute(
            text("UPDATE chats SET agent_id = 'agent-a' WHERE id = :chat_id"),
            {"chat_id": chat_id},
        )
        await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3, scope="current_agent"),
            agent_id="agent-b",
        )

        assert response.hits == []

    @pytest.mark.asyncio
    async def test_current_agent_scope_filters_null_agent(self, fts_db: AsyncSession):
        null_agent_chat_id = await seed_chat_and_messages(fts_db)
        other_chat_id = "chat-agent-b"
        fts_db.add(
            Chat(
                id=other_chat_id,
                title="Other agent Docker notes",
                action_mode="agent",
                agent_id="agent-b",
            )
        )
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
        )

        assert [hit.conversation_id for hit in response.hits] == [chat_id]
        assert "Bluegreen" in response.hits[0].snippet

    @pytest.mark.asyncio
    async def test_lineage_ancestors_restricts_recall_to_parent_chain(self, fts_db: AsyncSession):
        parent_id = "chat-parent"
        current_id = "chat-current"
        unrelated_id = "chat-unrelated"
        fts_db.add_all(
            [
                Chat(id=parent_id, title="Parent chat", action_mode="agent"),
                Chat(id=current_id, title="Current chat", action_mode="agent"),
                Chat(id=unrelated_id, title="Unrelated chat", action_mode="agent"),
                ConversationFork(
                    child_chat_id=current_id,
                    parent_chat_id=parent_id,
                    fork_message_index=0,
                ),
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

        response = await ConversationSearchService.search(
            ConversationSearchRequest(
                query="docker",
                limit=3,
                current_conversation_id=current_id,
                lineage="ancestors",
            ),
            agent_id=None,
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

    @pytest.mark.asyncio
    async def test_expand_message_window_returns_segments(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)

        response = await ConversationSearchService.search(
            ConversationSearchRequest(
                query="",
                expand_conversation_id=chat_id,
                expand_message_id="msg-3",
                expand_window=2,
            ),
            agent_id=None,
        )

        assert len(response.hits) == 1
        assert response.hits[0].message_id == "msg-3"
        assert "Kubernetes" in response.hits[0].snippet

    @pytest.mark.asyncio
    async def test_interactive_source_ranks_above_cron(self, fts_db: AsyncSession):
        cron_id = "chat-cron-alpha"
        web_id = "chat-web-alpha"
        now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
        fts_db.add_all(
            [
                Chat(
                    id=cron_id,
                    title="Cron alpha digest",
                    action_mode="agent",
                    source="cron",
                ),
                Chat(
                    id=web_id,
                    title="Web alpha planning",
                    action_mode="agent",
                    source="web",
                ),
            ]
        )
        fts_db.add_all(
            [
                Message(
                    id="msg-cron-alpha",
                    chat_id=cron_id,
                    role="assistant",
                    content="Alpha project cron summary for nightly automation.",
                    sent_at=now,
                    sent_timezone="UTC",
                ),
                Message(
                    id="msg-web-alpha",
                    chat_id=web_id,
                    role="assistant",
                    content="Alpha project planning notes from interactive chat.",
                    sent_at=now,
                    sent_timezone="UTC",
                ),
            ]
        )
        await fts_db.commit()
        await ConversationRecallRepository.rebuild_chat(fts_db, cron_id)
        await ConversationRecallRepository.rebuild_chat(fts_db, web_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="alpha project", limit=3),
            agent_id=None,
        )

        assert len(response.hits) >= 2
        assert response.hits[0].conversation_id == web_id
        assert response.hits[0].score >= response.hits[1].score

    @pytest.mark.asyncio
    async def test_fts_hits_use_rank_normalized_scores_and_index_source(self, fts_db: AsyncSession) -> None:
        await seed_chat_and_messages(fts_db)
        second_id = "chat-docker-second"
        fts_db.add(Chat(id=second_id, title="Second docker notes", action_mode="agent"))
        fts_db.add(
            Message(
                id="msg-docker-second",
                chat_id=second_id,
                role="assistant",
                content="Docker image layers explained.",
                sent_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
                sent_timezone="UTC",
            )
        )
        await fts_db.commit()
        await ConversationRecallRepository.rebuild_chat(fts_db, second_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3),
            agent_id=None,
        )

        # Deterministic RRF normalized to [0, 1]: 0.98 * 61 / (60 + rank).
        assert [hit.score for hit in response.hits] == pytest.approx([0.98, 0.98 * 61 / 62])
        assert {hit.source for hit in response.hits} == {"conversation_index"}
        assert all(hit.source_ref is not None and hit.source_ref.score == hit.score for hit in response.hits)
        assert response.recall_debug is not None
        assert response.recall_debug["fused_count"] == 2

        filtered = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3, min_score=0.97),
            agent_id=None,
        )
        assert [hit.conversation_id for hit in filtered.hits] == [response.hits[0].conversation_id]

    def test_source_interaction_boost_values(self) -> None:
        from app.services.chat.conversation_search_service import (
            _source_interaction_boost,
        )

        assert _source_interaction_boost("cron") == -0.10
        assert _source_interaction_boost("web") == 0.06
        assert _source_interaction_boost("kanban") == 0.0
        assert _source_interaction_boost(None) == 0.0

    @pytest.mark.asyncio
    async def test_conversation_history_search_provider_default_scope(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.services.chat.conversation_search_service import ConversationHistorySearchProvider

        provider = ConversationHistorySearchProvider(
            current_chat_id="chat-feishu-1",
            agent_id="agent-1",
            default_scope="same_source",
        )

        with patch.object(ConversationSearchService, "search", AsyncMock(return_value="mock_resp")) as mock_search:
            req = ConversationSearchRequest(query="test", limit=5)
            res = await provider.search(req)
            assert res == "mock_resp"
            mock_search.assert_called_once()
            passed_req = mock_search.call_args[0][0]
            assert passed_req.scope == "same_source"
            assert passed_req.current_conversation_id == "chat-feishu-1"

    @pytest.mark.asyncio
    async def test_search_and_recent_include_coverage_metadata(self, fts_db: AsyncSession) -> None:
        chat_id = await seed_chat_and_messages(fts_db)
        await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="Kubernetes", limit=3),
            agent_id=None,
        )

        assert response.coverage is not None
        assert response.coverage.total_conversations >= 1
        assert response.coverage.indexed_conversations >= 1
        assert response.coverage.coverage_ratio >= 0.0
        assert response.coverage.indexing_degraded is False
        assert response.recall_debug is not None
        assert "per_source" in response.recall_debug

        recent_response = await ConversationSearchService.search(
            ConversationSearchRequest(query="", limit=3),
            agent_id=None,
        )
        assert recent_response.coverage is not None
        assert recent_response.coverage.total_conversations >= 1

    @pytest.mark.asyncio
    async def test_search_expanded_window_end_to_end(self, fts_db: AsyncSession) -> None:
        chat_id = await seed_chat_and_messages(fts_db)
        await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()

        # Execute real database expand recall
        expand_response = await ConversationSearchService.search(
            ConversationSearchRequest(
                query="",
                expand_conversation_id=chat_id,
                expand_message_id="msg-1",
                expand_window=3,
            ),
            agent_id=None,
        )

        assert expand_response.mode == "search"
        assert len(expand_response.hits) == 1
        hit = expand_response.hits[0]
        assert hit.conversation_id == chat_id
        assert hit.message_id == "msg-1"
        assert hit.snippet is not None
        assert "user:" in hit.snippet or "assistant:" in hit.snippet
