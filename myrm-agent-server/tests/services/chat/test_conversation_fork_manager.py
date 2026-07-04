"""Unit tests for ConversationForkManager

P1-4: Basic test coverage for fork functionality.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database.models import Chat, ConversationFork, Message
from app.services.chat.conversation_fork_manager import (
    ConversationForkManager,
)


@pytest.mark.asyncio
async def test_fork_conversation_boundary_check(db_session, test_user):
    """Test message_index boundary validation (P1-5)."""
    # Create test chat with 5 messages
    chat_id = str(uuid4())
    chat = Chat(
        id=chat_id,
        title="Test Chat",
    )
    db_session.add(chat)

    now = datetime.now(timezone.utc)
    for i in range(5):
        msg = Message(
            id=str(uuid4()),
            chat_id=chat_id,
            role="user",
            content=f"Message {i}",
            sent_at=now,
            sent_timezone="UTC",
        )
        db_session.add(msg)

    await db_session.commit()

    # Test: message_index < 0 (invalid)
    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=-1,
    )

    assert not result.success
    assert "Invalid message_index" in result.error

    # Test: message_index >= total_messages (invalid)
    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=10,
    )

    assert not result.success
    assert "Invalid message_index" in result.error


@pytest.mark.asyncio
async def test_fork_conversation_from_any_message(db_session, test_user, monkeypatch):
    """Test that fork works from any valid message index."""
    monkeypatch.setattr(
        "app.services.chat.conversation_fork_manager.get_checkpointer",
        lambda: None,
        raising=False,
    )
    try:
        from app import platform_utils
        monkeypatch.setattr(platform_utils, "get_checkpointer", lambda: None)
    except Exception:
        pass

    chat_id = str(uuid4())
    chat = Chat(
        id=chat_id,
        title="Test Chat",
    )
    db_session.add(chat)

    now = datetime.now(timezone.utc)
    for i in range(5):
        msg = Message(
            id=str(uuid4()),
            chat_id=chat_id,
            role="user",
            content=f"Message {i}",
            sent_at=now,
            sent_timezone="UTC",
        )
        db_session.add(msg)

    await db_session.commit()

    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=2,
    )

    assert result.success
    assert result.new_chat_id is not None
    assert result.fork_point == 2


@pytest.mark.asyncio
async def test_fork_conversation_copies_session_loaded_skill_names(
    db_session,
    test_user,
    monkeypatch,
) -> None:
    """Forked chat inherits parent session_loaded_skill_names SSOT."""
    monkeypatch.setattr(
        "app.services.chat.conversation_fork_manager.get_checkpointer",
        lambda: None,
        raising=False,
    )
    try:
        from app import platform_utils

        monkeypatch.setattr(platform_utils, "get_checkpointer", lambda: None)
    except Exception:
        pass

    chat_id = str(uuid4())
    parent = Chat(
        id=chat_id,
        title="Parent",
        session_loaded_skill_names=["rail_skill", "pdf_skill"],
    )
    db_session.add(parent)

    now = datetime.now(timezone.utc)
    for i in range(3):
        db_session.add(
            Message(
                id=str(uuid4()),
                chat_id=chat_id,
                role="user",
                content=f"Message {i}",
                sent_at=now,
                sent_timezone="UTC",
            )
        )

    await db_session.commit()

    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=1,
    )

    assert result.success
    assert result.new_chat_id is not None

    child_stmt = select(Chat).where(Chat.id == result.new_chat_id)
    child_result = await db_session.execute(child_stmt)
    child_chat = child_result.scalar_one()

    assert child_chat.session_loaded_skill_names == ["rail_skill", "pdf_skill"]


@pytest.mark.asyncio
async def test_get_fork_info_no_fork(db_session, test_user):
    """Test get_fork_info for non-forked chat."""
    chat_id = str(uuid4())
    chat = Chat(
        id=chat_id,
        title="Test Chat",
    )
    db_session.add(chat)
    await db_session.commit()

    fork_info = await ConversationForkManager.get_fork_info(db_session, chat_id)

    assert fork_info.parent_chat_id is None
    assert fork_info.fork_point is None
    assert len(fork_info.children) == 0


@pytest.mark.asyncio
async def test_get_fork_info_with_children(db_session, test_user):
    """Test get_fork_info returns child forks."""
    # Create parent chat
    parent_id = str(uuid4())
    parent_chat = Chat(
        id=parent_id,
        title="Parent Chat",
    )
    db_session.add(parent_chat)

    # Create 2 child forks
    child_ids = []
    for i in range(2):
        child_id = str(uuid4())
        child_chat = Chat(
            id=child_id,
            title=f"Child {i}",
        )
        db_session.add(child_chat)

        fork_record = ConversationFork(
            child_chat_id=child_id,
            parent_chat_id=parent_id,
            fork_checkpoint_id="test-checkpoint",
            fork_message_index=i,
        )
        db_session.add(fork_record)
        child_ids.append(child_id)

    await db_session.commit()

    # Get fork info for parent
    fork_info = await ConversationForkManager.get_fork_info(db_session, parent_id)

    assert fork_info.parent_chat_id is None  # Parent has no parent
    assert len(fork_info.children) == 2
    assert set(c.chat_id for c in fork_info.children) == set(child_ids)


@pytest.mark.asyncio
async def test_get_fork_info_child(db_session, test_user):
    """Test get_fork_info for child chat returns parent."""
    # Create parent and child
    parent_id = str(uuid4())
    child_id = str(uuid4())

    parent_chat = Chat(id=parent_id, title="Parent")
    child_chat = Chat(id=child_id, title="Child")

    db_session.add(parent_chat)
    db_session.add(child_chat)

    fork_record = ConversationFork(
        child_chat_id=child_id,
        parent_chat_id=parent_id,
        fork_checkpoint_id="test-checkpoint",
        fork_message_index=3,
    )
    db_session.add(fork_record)

    await db_session.commit()

    # Get fork info for child
    fork_info = await ConversationForkManager.get_fork_info(db_session, child_id)

    assert fork_info.parent_chat_id == parent_id
    assert fork_info.fork_point == 3
    assert len(fork_info.children) == 0  # Child has no children


@pytest.fixture
def test_user():
    """Provide a test user ID (single-user architecture, no User model)."""
    from types import SimpleNamespace

    return SimpleNamespace(id=str(uuid4()))
