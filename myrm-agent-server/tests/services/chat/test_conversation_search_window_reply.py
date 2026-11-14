"""An empty sessions search under an explicit since/until window names that window, on the real service stack.

The agent reaches the conversation index through `search_sessions_corpus`, the production
`ConversationHistorySearchProvider` and the FTS recall index; the service blames relevance for an empty search whether
the query matched nothing or the window excluded the match, so only the reply can tell the model which one it was.
The window bounds the time of a conversation's last message, not the chat row's own timestamps or any earlier message.
"""

from datetime import UTC, datetime

import pytest
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution import search_sessions_corpus
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchBackends
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat.conversation_search_service import ConversationHistorySearchProvider
from tests.services.chat.search_support import seed_chat_and_messages

# The seeded messages were sent on 2026-04-17, so the window from _SINCE to _UNTIL excludes all of them.
_SINCE = datetime(2026, 12, 10, tzinfo=UTC)
_UNTIL = datetime(2026, 12, 24, tzinfo=UTC)
_WINDOW_NOTE = (
    "This search was limited to conversations whose last message was sent after 2026-12-10 00:00 UTC and before "
    "2026-12-24 00:00 UTC: other conversations are not returned, even if part of them falls inside that period. "
    "If what you need may be outside that period, retry without since/until."
)


async def _sessions(
    query: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    expand_conversation_id: str | None = None,
    expand_message_id: str | None = None,
) -> str:
    backends = MemorySearchBackends(conversation_provider=ConversationHistorySearchProvider(current_chat_id=None, agent_id=None))
    result = await search_sessions_corpus(
        backends,
        query=query,
        limit=5,
        since=since,
        until=until,
        expand_conversation_id=expand_conversation_id,
        expand_message_id=expand_message_id,
    )
    return str(result["content"]) if isinstance(result, dict) else result


@pytest.mark.asyncio
async def test_a_search_whose_window_excludes_the_conversation_names_the_window(fts_db: AsyncSession) -> None:
    await seed_chat_and_messages(fts_db)

    assert "Docker deployment discussion" in await _sessions("docker")
    assert await _sessions("docker", since=_SINCE, until=_UNTIL) == (
        f"No sufficiently relevant previous conversations found.\n{_WINDOW_NOTE}"
    )


@pytest.mark.asyncio
async def test_a_recent_listing_whose_window_excludes_the_conversation_names_the_window(fts_db: AsyncSession) -> None:
    await seed_chat_and_messages(fts_db)

    assert "Docker deployment discussion" in await _sessions("*")
    assert await _sessions("*", since=_SINCE, until=_UNTIL) == f"No previous conversations found.\n{_WINDOW_NOTE}"


@pytest.mark.asyncio
async def test_expanding_a_message_ignores_the_window(fts_db: AsyncSession) -> None:
    chat_id = await seed_chat_and_messages(fts_db)

    reply = await _sessions("", expand_conversation_id=chat_id, expand_message_id="msg-3", since=_SINCE, until=_UNTIL)

    assert "What about Kubernetes deployment?" in reply
    assert "limited to conversations" not in reply


@pytest.mark.asyncio
async def test_a_refused_expand_is_not_blamed_on_the_window(fts_db: AsyncSession) -> None:
    chat_id = await seed_chat_and_messages(fts_db)

    reply = await _sessions("", expand_conversation_id=chat_id, expand_message_id="no-such-message", since=_SINCE, until=_UNTIL)

    assert reply == "No visible messages found for the requested expand window."


# A window that covers the seeded messages (2026-04-17), so only a later last message can move a conversation out of it.
_COVERING_SINCE = datetime(2026, 4, 10, tzinfo=UTC)
_COVERING_UNTIL = datetime(2026, 4, 24, tzinfo=UTC)


@pytest.mark.asyncio
async def test_a_conversation_that_continued_past_the_window_is_left_out(fts_db: AsyncSession) -> None:
    await seed_chat_and_messages(fts_db, last_sent_at=datetime(2026, 4, 30, 12, tzinfo=UTC))

    reply = await _sessions("docker", since=_COVERING_SINCE, until=_COVERING_UNTIL)

    assert "Docker deployment discussion" not in reply
    assert "sent after 2026-04-10 00:00 UTC and before 2026-04-24 00:00 UTC" in reply


@pytest.mark.asyncio
async def test_a_conversation_whose_last_message_is_inside_the_window_is_returned(fts_db: AsyncSession) -> None:
    # The chat row's own timestamps are set when the test runs, far outside the window: only its last message is inside.
    await seed_chat_and_messages(fts_db)

    assert "Docker deployment discussion" in await _sessions("docker", since=_COVERING_SINCE, until=_COVERING_UNTIL)
