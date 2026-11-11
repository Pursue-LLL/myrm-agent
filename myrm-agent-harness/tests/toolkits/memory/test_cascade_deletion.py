"""Unit tests for cascade deletion (purge_by_source_chat_id / count_by_source_chat_id).

Tests cover:
- SQLiteRelationalStore.delete_pending_by_source_chat_id
- SQLiteRelationalStore.count_pending_by_source_chat_id
- SQLiteRelationalStore.delete_profiles_by_source_chat_id, count_profiles_by_source_chat_id
- MemoryManagerDeletionMixin.purge_by_source_chat_id (including closing the chat to later writers)
- MemoryManagerDeletionMixin.count_by_source_chat_id
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from myrm_agent_harness.toolkits.memory.relational.sqlite_store import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import is_closed
from myrm_agent_harness.toolkits.memory.types import MemoryScope, MemoryType, PendingRecord


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "test_cascade.db")


@pytest.fixture
async def store(tmp_db: str):
    s = SQLiteRelationalStore(db_path=tmp_db)
    await s._get_connection()
    try:
        yield s
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_delete_pending_by_source_chat_id_empty(store: SQLiteRelationalStore) -> None:
    result = await store.delete_pending_by_source_chat_id("nonexistent-chat")
    assert result == 0


@pytest.mark.asyncio
async def test_count_pending_by_source_chat_id_empty(store: SQLiteRelationalStore) -> None:
    result = await store.count_pending_by_source_chat_id("nonexistent-chat")
    assert result == 0


@pytest.mark.asyncio
async def test_delete_pending_by_source_chat_id(store: SQLiteRelationalStore) -> None:
    chat_id = "test-chat-123"
    for i in range(3):
        record = PendingRecord(
            id=f"pending-{i}",
            user_id="default",
            memory_type=MemoryType.SEMANTIC,
            content=f"Test content {i}",
            source_chat_id=chat_id,
        )
        await store.submit_pending(record)

    other_record = PendingRecord(
        id="pending-other",
        user_id="default",
        memory_type=MemoryType.SEMANTIC,
        content="Other content",
        source_chat_id="other-chat",
    )
    await store.submit_pending(other_record)

    deleted = await store.delete_pending_by_source_chat_id(chat_id)
    assert deleted == 3

    remaining = await store.count_pending_by_source_chat_id("other-chat")
    assert remaining == 1


@pytest.mark.asyncio
async def test_count_pending_by_source_chat_id(store: SQLiteRelationalStore) -> None:
    chat_id = "test-chat-456"
    for i in range(5):
        record = PendingRecord(
            id=f"count-pending-{i}",
            user_id="default",
            memory_type=MemoryType.EPISODIC,
            content=f"Count content {i}",
            source_chat_id=chat_id,
        )
        await store.submit_pending(record)

    count = await store.count_pending_by_source_chat_id(chat_id)
    assert count == 5

    count_other = await store.count_pending_by_source_chat_id("no-such-chat")
    assert count_other == 0


@pytest.mark.asyncio
async def test_delete_pending_with_null_source_chat_id(store: SQLiteRelationalStore) -> None:
    """Records with NULL source_chat_id should NOT be deleted."""
    record = PendingRecord(
        id="pending-null",
        user_id="default",
        memory_type=MemoryType.SEMANTIC,
        content="No source chat",
        source_chat_id=None,
    )
    await store.submit_pending(record)

    deleted = await store.delete_pending_by_source_chat_id("any-chat")
    assert deleted == 0

    total = await store.count_pending()
    assert total == 1


@pytest.mark.asyncio
async def test_profiles_leave_with_the_chat_they_were_written_from(store: SQLiteRelationalStore) -> None:
    await store.set_profile("__working_state", "digest of chat a", source_chat_id="chat-a")
    await store.set_profile("__working_state_updated_at", "2026-11-11T00:00:00Z", source_chat_id="chat-a")
    await store.set_profile("reply_style", "brief", source_chat_id="chat-b")
    await store.set_profile("timezone", "UTC+8")

    assert await store.count_profiles_by_source_chat_id("chat-a") == 2
    assert await store.delete_profiles_by_source_chat_id("chat-a") == 2

    assert await store.count_profiles_by_source_chat_id("chat-a") == 0
    assert await store.get_profile("__working_state") is None
    assert await store.get_profile("reply_style") == "brief"
    assert await store.get_profile("timezone") == "UTC+8"


@pytest.mark.asyncio
async def test_a_write_replaces_the_chat_link_of_the_value(store: SQLiteRelationalStore) -> None:
    await store.set_profile("__working_state", "from chat a", source_chat_id="chat-a")
    await store.set_profile("__working_state", "the user's own text")
    assert await store.delete_profiles_by_source_chat_id("chat-a") == 0
    assert await store.get_profile("__working_state") == "the user's own text"

    await store.set_profile("__working_state", "from chat b", source_chat_id="chat-b")
    assert await store.delete_profiles_by_source_chat_id("chat-a") == 0
    assert await store.delete_profiles_by_source_chat_id("chat-b") == 1
    assert await store.get_profile("__working_state") is None


@pytest.mark.asyncio
async def test_the_entry_of_every_namespace_leaves_with_its_chat(store: SQLiteRelationalStore) -> None:
    for agent in ("a", "b"):
        scope = MemoryScope(primary_namespace=f"agent:{agent}", namespaces=["global", f"agent:{agent}"])
        await store.set_profile("__working_state", f"digest for {agent}", scope=scope, source_chat_id="chat-a")

    assert await store.count_profiles_by_source_chat_id("chat-a") == 2
    assert await store.delete_profiles_by_source_chat_id("chat-a") == 2
    assert await store.get_profile("__working_state") is None


@pytest.mark.asyncio
async def test_purge_by_source_chat_id_integration() -> None:
    """The purge deletes through both chat links and the chat's pending records."""
    from myrm_agent_harness.toolkits.memory._manager.deletion import MemoryManagerDeletionMixin

    mixin = MagicMock(spec=MemoryManagerDeletionMixin)
    mixin._user_id = "u1"
    mixin._graph = None
    mixin.delete_memories_by_metadata = AsyncMock(side_effect=[{"semantic": 2, "episodic": 1}, {"semantic": 1}])
    mixin._vector = None
    mixin._relational = MagicMock()
    mixin._relational.delete_pending_by_source_chat_id = AsyncMock(return_value=3)
    mixin._relational.delete_profiles_by_source_chat_id = AsyncMock(return_value=2)

    result = await MemoryManagerDeletionMixin.purge_by_source_chat_id(mixin, "chat-xyz")

    assert result == {"semantic": 3, "episodic": 1, "pending": 3, "profile": 2}
    assert is_closed("u1", "chat-xyz")
    assert mixin.delete_memories_by_metadata.await_args_list == [
        call("source_chat_id", "chat-xyz", memory_types=None),
        call(
            "source_chat_ids",
            "chat-xyz",
            memory_types=(MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL),
        ),
    ]
    mixin._relational.delete_pending_by_source_chat_id.assert_called_once_with("chat-xyz")
    mixin._relational.delete_profiles_by_source_chat_id.assert_called_once_with("chat-xyz")


@pytest.mark.asyncio
async def test_purge_by_source_chat_id_no_relational() -> None:
    """When relational store is None, only vector deletion runs."""
    from myrm_agent_harness.toolkits.memory._manager.deletion import MemoryManagerDeletionMixin

    mixin = MagicMock(spec=MemoryManagerDeletionMixin)
    mixin._user_id = "u1"
    mixin._graph = None
    mixin.delete_memories_by_metadata = AsyncMock(side_effect=[{"semantic": 1}, {}])
    mixin._vector = None
    mixin._relational = None

    result = await MemoryManagerDeletionMixin.purge_by_source_chat_id(mixin, "chat-abc")

    assert result == {"semantic": 1}
    assert "pending" not in result


@pytest.mark.asyncio
async def test_a_failing_cascade_step_does_not_stop_the_others() -> None:
    """A failing chat link or buffer purge is skipped; the other steps still delete."""
    from myrm_agent_harness.toolkits.memory._manager.deletion import MemoryManagerDeletionMixin

    mixin = MagicMock(spec=MemoryManagerDeletionMixin)
    mixin.delete_memories_by_metadata = AsyncMock(side_effect=[RuntimeError("vector down"), {"semantic": 1}])
    mixin._user_id = "u1"
    mixin._graph = None
    mixin._config = MagicMock(collection_prefix="memory")
    mixin._vector = MagicMock()
    mixin._vector.delete_by_filter = AsyncMock(side_effect=RuntimeError("buffer down"))
    mixin._relational = MagicMock()
    mixin._relational.delete_pending_by_source_chat_id = AsyncMock(return_value=2)
    mixin._relational.delete_profiles_by_source_chat_id = AsyncMock(return_value=0)

    result = await MemoryManagerDeletionMixin.purge_by_source_chat_id(mixin, "chat-x")

    assert result == {"semantic": 1, "pending": 2}
    assert is_closed("u1", "chat-x")
    mixin._vector.delete_by_filter.assert_awaited_once_with(
        "memory_recurrence_buffer", {"user_id": "u1", "source_chat_id": "chat-x"}
    )


@pytest.mark.asyncio
async def test_count_by_source_chat_id_integration() -> None:
    """Test count_by_source_chat_id orchestrates vector + relational counting."""
    from myrm_agent_harness.toolkits.memory._manager.deletion import MemoryManagerDeletionMixin

    mixin = MagicMock(spec=MemoryManagerDeletionMixin)
    mixin.list_memory_ids_by_metadata = AsyncMock(return_value={"semantic": ["id1", "id2"], "episodic": ["id3"]})
    mixin._relational = MagicMock()
    mixin._relational.count_pending_by_source_chat_id = AsyncMock(return_value=4)
    mixin._relational.count_profiles_by_source_chat_id = AsyncMock(return_value=2)

    result = await MemoryManagerDeletionMixin.count_by_source_chat_id(mixin, "chat-count")

    assert result == {"semantic": 2, "episodic": 1, "pending": 4, "profile": 2}


@pytest.mark.asyncio
async def test_count_by_source_chat_id_no_pending() -> None:
    """When pending count is 0, it should not appear in result."""
    from myrm_agent_harness.toolkits.memory._manager.deletion import MemoryManagerDeletionMixin

    mixin = MagicMock(spec=MemoryManagerDeletionMixin)
    mixin.list_memory_ids_by_metadata = AsyncMock(return_value={"semantic": ["id1"]})
    mixin._relational = MagicMock()
    mixin._relational.count_pending_by_source_chat_id = AsyncMock(return_value=0)
    mixin._relational.count_profiles_by_source_chat_id = AsyncMock(return_value=0)

    result = await MemoryManagerDeletionMixin.count_by_source_chat_id(mixin, "chat-zero")

    assert result == {"semantic": 1}
    assert "pending" not in result
    assert "profile" not in result
