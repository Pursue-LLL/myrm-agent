"""Everyday punctuation typed into a search box.

A query such as ``don't``, ``e.g.`` or ``hello world.`` is searched as typed: the search dialog and the ``@chat:`` picker
both find the chat that says it, and the picker answers from the index without rebuilding it. A query too short to have a
trigram (``a.``) is read by the LIKE fallback on the typed text; ``test_search_typed_text.py`` pins that fallback in every
search entry.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat.chat_service import ChatService
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService
from tests.services.chat.search_support import seed_chat_with_text

_CHAT = "chat-punctuation"
# Three characters or more, so the trigram index answers.
_INDEXED = ("don't", "it's", "I'm", "John's", "e.g.", "i.e.", "etc.", "Inc.", "hello world.", "v2.0.")
# Under three characters there is no trigram: only the LIKE fallback can find these.
_SHORT = ("a.", "U.", "'s")


async def _seed(db: AsyncSession, phrase: str) -> None:
    await seed_chat_with_text(db, _CHAT, f"We discussed {phrase} during the planning meeting yesterday", "noted")


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]


@pytest.fixture
def rebuild_statements(fts_db: AsyncSession) -> Iterator[list[str]]:
    """The FTS ``rebuild`` statements the database engine runs."""
    statements: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, _parameters: object, _context: object, _many: bool) -> None:
        if "'rebuild'" in statement:
            statements.append(statement)

    engine = fts_db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    yield statements
    event.remove(engine, "before_cursor_execute", record)


@pytest.mark.parametrize("phrase", _INDEXED)
@pytest.mark.asyncio
async def test_the_search_dialog_finds_what_was_typed(
    fts_db: AsyncSession, caplog: pytest.LogCaptureFixture, phrase: str
) -> None:
    await _seed(fts_db, phrase)

    with caplog.at_level(logging.WARNING):
        items, _total = await ChatService.search_messages(phrase)

    assert {str(item["chat_id"]) for item in items} == {_CHAT}
    assert _warnings(caplog) == []


@pytest.mark.parametrize("phrase", [*_INDEXED, *_SHORT])
@pytest.mark.asyncio
async def test_the_chat_picker_finds_it_without_rebuilding_an_index(
    fts_db: AsyncSession, rebuild_statements: list[str], caplog: pytest.LogCaptureFixture, phrase: str
) -> None:
    await _seed(fts_db, phrase)
    rebuild_statements.clear()

    with caplog.at_level(logging.WARNING):
        items, _total = await ConversationRecallIndexService.search_citable_chats(phrase)

    assert {str(item["chat_id"]) for item in items} == {_CHAT}
    assert rebuild_statements == []
    assert _warnings(caplog) == []
