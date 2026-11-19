"""ConversationSearchService ranking tests: which hit comes first and the score it gets."""

from datetime import datetime, timezone

import pytest
from myrm_agent_harness.toolkits.memory.conversation_search import (
    ConversationSearchRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.database.repositories.conversation_recall import ConversationRecallRepository
from app.services.chat.conversation_search_service import ConversationSearchService
from tests.services.chat.search_support import seed_chat_and_messages


class TestConversationSearchRanking:
    @pytest.mark.asyncio
    async def test_interactive_source_ranks_above_cron(self, fts_db: AsyncSession) -> None:
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
    async def test_the_strongest_match_ranks_first(self, fts_db: AsyncSession) -> None:
        """A chat packed with the query outranks one that mentions it once inside a long conversation."""
        now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
        matching = {
            "chat-docker-strong": "docker " * 30 + "deployment",
            "chat-docker-mid": "docker " * 6 + "deployment notes about compose files",
            "chat-docker-weak": "docker " + " ".join(f"background{i}" for i in range(150)),
        }
        unrelated = {f"chat-planning-{i}": f"weekly planning notes number {i} about the roadmap" for i in range(60)}
        everything = {**matching, **unrelated}
        fts_db.add_all([Chat(id=chat_id, title=chat_id, action_mode="agent", source="web") for chat_id in everything])
        fts_db.add_all(
            [
                Message(
                    id=f"msg-{chat_id}",
                    chat_id=chat_id,
                    role="assistant",
                    content=content,
                    sent_at=now,
                    sent_timezone="UTC",
                )
                for chat_id, content in everything.items()
            ]
        )
        await fts_db.commit()
        for chat_id in everything:
            await ConversationRecallRepository.rebuild_chat(fts_db, chat_id)
        await fts_db.commit()

        response = await ConversationSearchService.search(
            ConversationSearchRequest(query="docker", limit=3),
            agent_id=None,
        )

        assert [hit.conversation_id for hit in response.hits] == list(matching)

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
        from app.services.chat.conversation_search_hits import source_interaction_boost

        assert source_interaction_boost("cron") == -0.10
        assert source_interaction_boost("web") == 0.06
        assert source_interaction_boost("kanban") == 0.0
        assert source_interaction_boost(None) == 0.0
