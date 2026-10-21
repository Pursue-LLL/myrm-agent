from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.database.repositories.chat_message_search_repo import ChatMessageSearchRepository


@pytest.mark.asyncio
async def test_search_messages_fts_excludes_incognito(db_session: AsyncSession):
    """Test that FTS search strictly excludes messages from incognito chats."""

    # 1. Create a normal chat
    normal_chat = Chat(
        id="normal_chat_1",
        title="Normal Chat",
        is_incognito=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(normal_chat)

    # 2. Create an incognito chat
    incognito_chat = Chat(
        id="incognito_chat_1",
        title="Incognito Chat",
        is_incognito=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(incognito_chat)

    await db_session.commit()

    # 3. Add messages with the same keyword
    msg1 = Message(
        id="msg_normal",
        chat_id="normal_chat_1",
        role="user",
        content="This is a secret_keyword in normal chat",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        is_active=True,
    )
    db_session.add(msg1)

    msg2 = Message(
        id="msg_incognito",
        chat_id="incognito_chat_1",
        role="user",
        content="This is a secret_keyword in incognito chat",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        is_active=True,
    )
    db_session.add(msg2)

    await db_session.commit()

    # 4. Search for the keyword
    messages, total = await ChatMessageSearchRepository.search_messages_fts(
        db=db_session,
        safe_query="secret_keyword",
        limit=10,
        offset=0,
        since=None,
        until=None,
    )

    # 5. Verify only the normal message is returned
    assert total == 1
    assert len(messages) == 1
    assert messages[0]["id"] == "msg_normal"
    assert messages[0]["chat_id"] == "normal_chat_1"
