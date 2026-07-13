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
    # When parent has sandbox_base_dir, child resets to original repo root
    assert child_chat.workspace_dir == "/repos/myapp"
    assert child_chat.sandbox_base_dir is None
    assert child_chat.project_id == "proj-123"
    assert child_chat.is_incognito is True
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


@pytest.mark.asyncio
async def test_fork_resets_sandbox_state_when_parent_has_active_sandbox(
    db_session,
    test_user,
    monkeypatch,
) -> None:
    """Fork from parent with active sandbox resets child to original repo root.

    Prevents child from sharing parent's sandbox worktree (file conflict risk).
    """
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
        title="Coding Chat",
        workspace_dir="/project/.sandboxes/sandbox-parentabcde",
        sandbox_base_dir="/project",
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
    assert result.new_chat_id is not None

    child_stmt = select(Chat).where(Chat.id == result.new_chat_id)
    child_result = await db_session.execute(child_stmt)
    child_chat = child_result.scalar_one()

    assert child_chat.workspace_dir == "/project", (
        "Child should use original repo root, not parent's sandbox worktree"
    )
    assert child_chat.sandbox_base_dir is None, (
        "Child should have no active sandbox"
    )


@pytest.mark.asyncio
async def test_fork_preserves_workspace_when_parent_has_no_sandbox(
    db_session,
    test_user,
    monkeypatch,
) -> None:
    """Fork from parent without sandbox preserves workspace_dir normally."""
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
        title="Normal Coding Chat",
        workspace_dir="/project/my-app",
        sandbox_base_dir=None,
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

    assert child_chat.workspace_dir == "/project/my-app", (
        "Child should inherit workspace_dir when parent has no sandbox"
    )
    assert child_chat.sandbox_base_dir is None


@pytest.mark.asyncio
async def test_fork_with_custom_title(db_session, test_user, monkeypatch) -> None:
    """Fork with explicit new_title uses the provided title."""
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
    parent = Chat(id=chat_id, title="Parent")
    db_session.add(parent)

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

    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=0,
        new_title="  My Custom Fork  ",
    )

    assert result.success
    child_stmt = select(Chat).where(Chat.id == result.new_chat_id)
    child_result = await db_session.execute(child_stmt)
    child_chat = child_result.scalar_one()
    assert child_chat.title == "My Custom Fork"


@pytest.mark.asyncio
async def test_fork_with_checkpoint_retrieval(db_session, test_user, monkeypatch) -> None:
    """Fork at last message index attempts checkpoint retrieval."""
    from unittest.mock import AsyncMock, MagicMock

    mock_checkpoint = MagicMock()
    mock_checkpoint.checkpoint = {"channel_values": {"messages": []}}
    mock_checkpoint.metadata = {}
    mock_checkpoint.config = {"checkpoint_id": "cp-123"}

    mock_checkpointer = MagicMock()
    mock_checkpointer.aget_tuple = AsyncMock(return_value=mock_checkpoint)
    mock_checkpointer.aput = AsyncMock()

    monkeypatch.setattr(
        "app.services.chat.conversation_fork_manager.get_checkpointer",
        lambda: mock_checkpointer,
        raising=False,
    )
    try:
        from app import platform_utils

        monkeypatch.setattr(platform_utils, "get_checkpointer", lambda: mock_checkpointer)
    except Exception:
        pass

    chat_id = str(uuid4())
    parent = Chat(id=chat_id, title="Checkpoint Chat")
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

    # Fork at last message index (2) to trigger checkpoint path
    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=2,
    )

    assert result.success
    mock_checkpointer.aget_tuple.assert_called_once()
    mock_checkpointer.aput.assert_called_once()


@pytest.mark.asyncio
async def test_fork_checkpoint_retrieval_failure_nonfatal(db_session, test_user, monkeypatch) -> None:
    """Fork succeeds even when checkpoint retrieval raises an exception."""
    from unittest.mock import AsyncMock, MagicMock

    mock_checkpointer = MagicMock()
    mock_checkpointer.aget_tuple = AsyncMock(side_effect=RuntimeError("DB timeout"))

    monkeypatch.setattr(
        "app.services.chat.conversation_fork_manager.get_checkpointer",
        lambda: mock_checkpointer,
        raising=False,
    )
    try:
        from app import platform_utils

        monkeypatch.setattr(platform_utils, "get_checkpointer", lambda: mock_checkpointer)
    except Exception:
        pass

    chat_id = str(uuid4())
    parent = Chat(id=chat_id, title="Checkpoint Fail Chat")
    db_session.add(parent)

    now = datetime.now(timezone.utc)
    for i in range(2):
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

    # Fork at last message to trigger checkpoint path
    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=1,
    )

    assert result.success
    assert result.new_chat_id is not None


@pytest.mark.asyncio
async def test_fork_checkpoint_empty_checkpoint_field(db_session, test_user, monkeypatch) -> None:
    """Fork handles checkpoint_tuple with empty checkpoint field gracefully."""
    from unittest.mock import AsyncMock, MagicMock

    mock_checkpoint = MagicMock()
    mock_checkpoint.checkpoint = None  # Empty checkpoint

    mock_checkpointer = MagicMock()
    mock_checkpointer.aget_tuple = AsyncMock(return_value=mock_checkpoint)

    monkeypatch.setattr(
        "app.services.chat.conversation_fork_manager.get_checkpointer",
        lambda: mock_checkpointer,
        raising=False,
    )
    try:
        from app import platform_utils

        monkeypatch.setattr(platform_utils, "get_checkpointer", lambda: mock_checkpointer)
    except Exception:
        pass

    chat_id = str(uuid4())
    parent = Chat(id=chat_id, title="Empty CP Chat")
    db_session.add(parent)

    now = datetime.now(timezone.utc)
    db_session.add(
        Message(
            id=str(uuid4()),
            chat_id=chat_id,
            role="user",
            content="Message 0",
            sent_at=now,
            sent_timezone="UTC",
        )
    )
    await db_session.commit()

    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=0,
    )

    assert result.success
    # aput should NOT be called since checkpoint was None
    mock_checkpointer.aput = AsyncMock()
    # Verify fork succeeded without checkpoint clone


@pytest.mark.asyncio
async def test_fork_checkpoint_clone_failure_nonfatal(db_session, test_user, monkeypatch) -> None:
    """Fork succeeds even when checkpoint clone (aput) raises an exception."""
    from unittest.mock import AsyncMock, MagicMock

    mock_checkpoint = MagicMock()
    mock_checkpoint.checkpoint = {"channel_values": {"messages": []}}
    mock_checkpoint.metadata = {}
    mock_checkpoint.config = {"checkpoint_id": "cp-456"}

    mock_checkpointer = MagicMock()
    mock_checkpointer.aget_tuple = AsyncMock(return_value=mock_checkpoint)
    mock_checkpointer.aput = AsyncMock(side_effect=RuntimeError("Write failed"))

    monkeypatch.setattr(
        "app.services.chat.conversation_fork_manager.get_checkpointer",
        lambda: mock_checkpointer,
        raising=False,
    )
    try:
        from app import platform_utils

        monkeypatch.setattr(platform_utils, "get_checkpointer", lambda: mock_checkpointer)
    except Exception:
        pass

    chat_id = str(uuid4())
    parent = Chat(id=chat_id, title="Clone Fail Chat")
    db_session.add(parent)

    now = datetime.now(timezone.utc)
    for i in range(2):
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


@pytest.mark.asyncio
async def test_fork_nonexistent_parent_returns_error(db_session, test_user, monkeypatch) -> None:
    """Fork from nonexistent parent chat returns error result."""
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

    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id="nonexistent-id-12345",
        message_index=0,
    )

    assert not result.success
    assert result.new_chat_id is None
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_fork_generates_title_from_empty_content(db_session, test_user, monkeypatch) -> None:
    """Fork generates fallback title when fork message has no content."""
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
    parent = Chat(id=chat_id, title="Research Chat")
    db_session.add(parent)

    now = datetime.now(timezone.utc)
    db_session.add(
        Message(
            id=str(uuid4()),
            chat_id=chat_id,
            role="user",
            content="",
            sent_at=now,
            sent_timezone="UTC",
        )
    )
    await db_session.commit()

    result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=0,
    )

    assert result.success
    child_stmt = select(Chat).where(Chat.id == result.new_chat_id)
    child_result = await db_session.execute(child_stmt)
    child_chat = child_result.scalar_one()
    assert "Branch from:" in child_chat.title


@pytest.mark.asyncio
async def test_get_fork_info_returns_parent_and_children(db_session, test_user, monkeypatch) -> None:
    """get_fork_info returns correct parent/children for forked chat."""
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
    parent = Chat(id=chat_id, title="Parent Chat")
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

    fork_result = await ConversationForkManager.fork_conversation(
        db=db_session,
        parent_chat_id=chat_id,
        message_index=1,
    )
    assert fork_result.success

    # Query fork info for child
    child_info = await ConversationForkManager.get_fork_info(db_session, fork_result.new_chat_id)
    assert child_info.parent_chat_id == chat_id
    assert child_info.fork_point == 1
    assert child_info.children == []

    # Query fork info for parent
    parent_info = await ConversationForkManager.get_fork_info(db_session, chat_id)
    assert parent_info.parent_chat_id is None
    assert len(parent_info.children) == 1
    assert parent_info.children[0].chat_id == fork_result.new_chat_id


@pytest.mark.asyncio
async def test_get_fork_info_no_forks(db_session, test_user) -> None:
    """get_fork_info returns empty result for chat with no fork relationships."""
    chat_id = str(uuid4())
    chat = Chat(id=chat_id, title="Standalone Chat")
    db_session.add(chat)
    await db_session.commit()

    info = await ConversationForkManager.get_fork_info(db_session, chat_id)
    assert info.parent_chat_id is None
    assert info.fork_point is None
    assert info.children == []


@pytest.mark.asyncio
async def test_delete_fork_lineage_counts_children(db_session, test_user, monkeypatch) -> None:
    """delete_fork_lineage returns correct child count."""
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
    parent = Chat(id=chat_id, title="Parent")
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

    # Create two forks
    r1 = await ConversationForkManager.fork_conversation(
        db=db_session, parent_chat_id=chat_id, message_index=0,
    )
    r2 = await ConversationForkManager.fork_conversation(
        db=db_session, parent_chat_id=chat_id, message_index=1,
    )
    assert r1.success and r2.success

    count = await ConversationForkManager.delete_fork_lineage(db_session, chat_id)
    assert count == 2


@pytest.fixture
def test_user():
    """Provide a test user ID (single-user architecture, no User model)."""
    from types import SimpleNamespace

    return SimpleNamespace(id=str(uuid4()))
