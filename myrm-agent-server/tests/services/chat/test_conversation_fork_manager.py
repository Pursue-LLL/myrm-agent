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


@pytest.mark.asyncio
async def test_fork_inherits_full_metadata(db_session, test_user, monkeypatch) -> None:
    """Forked chat inherits all critical metadata fields from parent."""
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
        action_mode="deep_research",
        workspace_dir="/projects/myapp",
        sandbox_base_dir="/repos/myapp",
        project_id="proj-123",
        is_incognito=True,
        task_adaptive_digest={"key": "value"},
        session_notes_json='{"notes": "test"}',
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
        message_index=2,
    )

    assert result.success
    child_stmt = select(Chat).where(Chat.id == result.new_chat_id)
    child_result = await db_session.execute(child_stmt)
    child_chat = child_result.scalar_one()

    assert child_chat.action_mode == "deep_research"
    assert child_chat.workspace_dir == "/projects/myapp"
    assert child_chat.sandbox_base_dir == "/repos/myapp"
    assert child_chat.project_id == "proj-123"
    assert child_chat.is_incognito is True
    assert child_chat.task_adaptive_digest == {"key": "value"}
    assert child_chat.session_notes_json == '{"notes": "test"}'


@pytest.mark.asyncio
async def test_fork_remaps_compacted_before_id(db_session, test_user, monkeypatch) -> None:
    """Forked chat remaps compacted_before_id to cloned message ID."""
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
    now = datetime.now(timezone.utc)

    msg_ids = [str(uuid4()) for _ in range(5)]
    compacted_msg_id = msg_ids[2]

    parent = Chat(
        id=chat_id,
        title="Long Chat",
        compacted_summary="Summary of first 3 messages",
        compacted_before_id=compacted_msg_id,
        compacted_at=now,
        compacted_tokens_saved=1500,
    )
    db_session.add(parent)

    for i, msg_id in enumerate(msg_ids):
        db_session.add(
            Message(
                id=msg_id,
                chat_id=chat_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
                sent_at=now,
                sent_timezone="UTC",
            )
        )
    await db_session.commit()

    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=4,
    )

    assert result.success
    child_stmt = select(Chat).where(Chat.id == result.new_chat_id)
    child_result = await db_session.execute(child_stmt)
    child_chat = child_result.scalar_one()

    assert child_chat.compacted_summary == "Summary of first 3 messages"
    assert child_chat.compacted_tokens_saved == 1500
    # compacted_before_id should be remapped to new cloned message ID
    assert child_chat.compacted_before_id != compacted_msg_id
    assert child_chat.compacted_before_id is not None

    # Verify the remapped ID exists in forked messages
    msg_stmt = select(Message).where(
        Message.chat_id == result.new_chat_id,
        Message.id == child_chat.compacted_before_id,
    )
    msg_result = await db_session.execute(msg_stmt)
    remapped_msg = msg_result.scalar_one_or_none()
    assert remapped_msg is not None
    assert remapped_msg.content == "Message 2"


@pytest.mark.asyncio
async def test_fork_clears_compaction_when_fork_before_compacted_point(
    db_session, test_user, monkeypatch
) -> None:
    """Fork before compaction boundary clears compaction fields to prevent stale reference."""
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
    now = datetime.now(timezone.utc)

    msg_ids = [str(uuid4()) for _ in range(10)]
    compacted_msg_id = msg_ids[6]

    parent = Chat(
        id=chat_id,
        title="Very Long Chat",
        compacted_summary="Summary of first 7 messages",
        compacted_before_id=compacted_msg_id,
        compacted_at=now,
        compacted_tokens_saved=3000,
    )
    db_session.add(parent)

    for i, msg_id in enumerate(msg_ids):
        db_session.add(
            Message(
                id=msg_id,
                chat_id=chat_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
                sent_at=now,
                sent_timezone="UTC",
            )
        )
    await db_session.commit()

    # Fork at message_index=3 (before compaction point at index 6)
    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=3,
    )

    assert result.success
    child_stmt = select(Chat).where(Chat.id == result.new_chat_id)
    child_result = await db_session.execute(child_stmt)
    child_chat = child_result.scalar_one()

    # Compaction fields should be cleared since fork point is before compacted boundary
    assert child_chat.compacted_summary is None
    assert child_chat.compacted_before_id is None
    assert child_chat.compacted_at is None
    assert child_chat.compacted_tokens_saved is None


@pytest.mark.asyncio
async def test_get_last_message_index_empty_chat(db_session, test_user):
    """get_last_message_index returns None for chat with zero messages."""
    chat_id = str(uuid4())
    chat = Chat(id=chat_id, title="Empty Chat")
    db_session.add(chat)
    await db_session.commit()

    result = await ConversationForkManager.get_last_message_index(db_session, chat_id)
    assert result is None


@pytest.mark.asyncio
async def test_get_last_message_index_single_message(db_session, test_user):
    """get_last_message_index returns 0 for chat with one message."""
    chat_id = str(uuid4())
    chat = Chat(id=chat_id, title="Single Msg Chat")
    db_session.add(chat)

    now = datetime.now(timezone.utc)
    db_session.add(
        Message(
            id=str(uuid4()),
            chat_id=chat_id,
            role="user",
            content="Hello",
            sent_at=now,
            sent_timezone="UTC",
        )
    )
    await db_session.commit()

    result = await ConversationForkManager.get_last_message_index(db_session, chat_id)
    assert result == 0


@pytest.mark.asyncio
async def test_get_last_message_index_multiple_messages(db_session, test_user):
    """get_last_message_index returns total-1 for chat with N messages."""
    chat_id = str(uuid4())
    chat = Chat(id=chat_id, title="Multi Msg Chat")
    db_session.add(chat)

    now = datetime.now(timezone.utc)
    for i in range(7):
        db_session.add(
            Message(
                id=str(uuid4()),
                chat_id=chat_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
                sent_at=now,
                sent_timezone="UTC",
            )
        )
    await db_session.commit()

    result = await ConversationForkManager.get_last_message_index(db_session, chat_id)
    assert result == 6


@pytest.fixture
def test_user():
    """Provide a test user ID (single-user architecture, no User model)."""
    from types import SimpleNamespace

    return SimpleNamespace(id=str(uuid4()))
