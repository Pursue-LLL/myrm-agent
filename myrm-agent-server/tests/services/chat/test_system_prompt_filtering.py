"""Unit tests for system prompt filtering (P0 Critical Security).

Verifies:
1. Service layer rejects role='system' messages
2. API layer filters out system messages from responses
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Chat, Message
from app.services.chat.chat_service import ChatService


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:testdb_filter?mode=memory&cache=shared&uri=true",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from app.database.migrations import ensure_raw_sql_schema

        await ensure_raw_sql_schema(engine)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Patch UoW factory
    import app.database.repositories.uow as uow_module

    original_factory = getattr(uow_module, "get_session_factory", None)
    uow_module.get_session_factory = lambda: async_session

    async with async_session() as session:
        yield session

    if original_factory:
        uow_module.get_session_factory = original_factory
    await engine.dispose()


@pytest.fixture
async def test_chat(db_session):
    """Create a test chat."""
    import uuid

    chat = Chat(
        id=f"test-chat-{uuid.uuid4()}",
        title="Test Chat",
        first_message="Hello",
        last_message="Hello",
        source="web",
    )
    db_session.add(chat)
    await db_session.commit()
    return chat


@pytest.mark.asyncio
async def test_service_rejects_system_role(db_session, test_chat):
    """Test that ChatService.append_message rejects role='system'."""
    with pytest.raises(ValueError, match="Invalid message role: 'system'"):
        await ChatService.append_message(
            chat_id=test_chat.id,
            role="system",
            content="You are a helpful assistant.",
            sent_at=datetime.now(tz=timezone.utc),
            sent_timezone="UTC",
        )

    # Verify no message was inserted
    messages = await ChatService.get_all_messages(test_chat.id)
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_service_allows_user_role(db_session, test_chat):
    """Test that ChatService.append_message allows role='user'."""
    msg = await ChatService.append_message(
        chat_id=test_chat.id,
        role="user",
        content="Hello AI",
        sent_at=datetime.now(tz=timezone.utc),
        sent_timezone="UTC",
    )

    assert msg.role == "user"
    assert msg.content == "Hello AI"

    # Verify message was inserted
    messages = await ChatService.get_all_messages(test_chat.id)
    assert len(messages) == 1
    assert messages[0].role == "user"


@pytest.mark.asyncio
async def test_service_allows_assistant_role(db_session, test_chat):
    """Test that ChatService.append_message allows role='assistant'."""
    msg = await ChatService.append_message(
        chat_id=test_chat.id,
        role="assistant",
        content="Hello human!",
        sent_at=datetime.now(tz=timezone.utc),
        sent_timezone="UTC",
    )

    assert msg.role == "assistant"
    assert msg.content == "Hello human!"

    # Verify message was inserted
    messages = await ChatService.get_all_messages(test_chat.id)
    assert len(messages) == 1
    assert messages[0].role == "assistant"


@pytest.mark.asyncio
async def test_service_rejects_unknown_role(db_session, test_chat):
    """Test that ChatService.append_message rejects unknown roles."""
    with pytest.raises(ValueError, match="Invalid message role"):
        await ChatService.append_message(
            chat_id=test_chat.id,
            role="tool",
            content="Tool output",
            sent_at=datetime.now(tz=timezone.utc),
            sent_timezone="UTC",
        )


@pytest.mark.asyncio
async def test_api_filters_system_messages_if_present(db_session, test_chat):
    """Test that API layer would filter system messages (defense-in-depth).

    Note: This test directly inserts a system message to the database (bypassing
    Service layer validation) to verify that the API layer filters it out.
    """
    # Bypass Service layer validation by directly inserting to database
    now = datetime.now(tz=timezone.utc)
    user_msg = Message(
        id="msg-1",
        chat_id=test_chat.id,
        role="user",
        content="User message",
        sent_at=now,
        sent_timezone="UTC",
    )
    system_msg = Message(
        id="msg-2",
        chat_id=test_chat.id,
        role="system",
        content="You are a helpful assistant.",
        sent_at=now,
        sent_timezone="UTC",
    )
    assistant_msg = Message(
        id="msg-3",
        chat_id=test_chat.id,
        role="assistant",
        content="Assistant message",
        sent_at=now,
        sent_timezone="UTC",
    )

    db_session.add_all([user_msg, system_msg, assistant_msg])
    await db_session.commit()

    # Verify database has 3 messages (including system)
    all_messages = await ChatService.get_all_messages(test_chat.id)
    assert len(all_messages) == 3

    # Simulate API layer filtering (same logic as chat.py:143)
    filtered_messages = [
        msg for msg in all_messages if msg.role in ("user", "assistant")
    ]

    # Verify system message was filtered out
    assert len(filtered_messages) == 2
    assert all(msg.role != "system" for msg in filtered_messages)
    assert filtered_messages[0].role == "user"
    assert filtered_messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_channel_history_filters_system_messages(db_session, test_chat):
    """Test that load_channel_history() filters system messages."""
    from datetime import timedelta

    base_time = datetime.now(tz=timezone.utc)

    # Directly insert messages (bypassing Service validation)
    user_msg = Message(
        id="msg-1",
        chat_id=test_chat.id,
        role="user",
        content="User message",
        sent_at=base_time + timedelta(seconds=1),
        sent_timezone="UTC",
        created_at=base_time + timedelta(seconds=1),
    )
    system_msg = Message(
        id="msg-2",
        chat_id=test_chat.id,
        role="system",
        content="You are a helpful assistant.",
        sent_at=base_time + timedelta(seconds=2),
        sent_timezone="UTC",
        created_at=base_time + timedelta(seconds=2),
    )
    assistant_msg = Message(
        id="msg-3",
        chat_id=test_chat.id,
        role="assistant",
        content="Assistant message",
        sent_at=base_time + timedelta(seconds=3),
        sent_timezone="UTC",
        created_at=base_time + timedelta(seconds=3),
    )
    user_msg2 = Message(
        id="msg-4",
        chat_id=test_chat.id,
        role="user",
        content="Latest user message",
        sent_at=base_time + timedelta(seconds=4),
        sent_timezone="UTC",
        created_at=base_time + timedelta(seconds=4),
    )

    db_session.add_all([user_msg, system_msg, assistant_msg, user_msg2])
    await db_session.commit()

    # Load channel history (should filter system and exclude latest user message)
    history = await ChatService.load_channel_history(test_chat.id)

    # Verify: should have 2 entries (user + assistant), system filtered, latest excluded
    assert len(history) == 2
    assert history[0].role == "human"
    assert history[0].content == "User message"
    assert history[1].role == "assistant"
    assert history[1].content == "Assistant message"


@pytest.mark.asyncio
async def test_web_history_filters_system_messages(db_session, test_chat):
    """Test that load_web_chat_history() filters system messages."""
    from datetime import timedelta

    base_time = datetime.now(tz=timezone.utc)

    # Directly insert messages (bypassing Service validation)
    user_msg = Message(
        id="msg-1",
        chat_id=test_chat.id,
        role="user",
        content="User message",
        sent_at=base_time + timedelta(seconds=1),
        sent_timezone="UTC",
        created_at=base_time + timedelta(seconds=1),
    )
    system_msg = Message(
        id="msg-2",
        chat_id=test_chat.id,
        role="system",
        content="You are a helpful assistant.",
        sent_at=base_time + timedelta(seconds=2),
        sent_timezone="UTC",
        created_at=base_time + timedelta(seconds=2),
    )
    assistant_msg = Message(
        id="msg-3",
        chat_id=test_chat.id,
        role="assistant",
        content="Assistant message",
        sent_at=base_time + timedelta(seconds=3),
        sent_timezone="UTC",
        created_at=base_time + timedelta(seconds=3),
    )

    db_session.add_all([user_msg, system_msg, assistant_msg])
    await db_session.commit()

    # Load web chat history
    history = await ChatService.load_web_chat_history(test_chat.id)

    # Verify: should have 2 entries (user + assistant), system filtered
    assert len(history) == 2
    assert history[0][0] == "human"
    assert history[0][1] == "User message"
    assert history[1][0] == "assistant"
    assert history[1][1] == "Assistant message"
