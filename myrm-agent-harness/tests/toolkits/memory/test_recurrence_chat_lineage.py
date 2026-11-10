"""A chat's deletion reaches what the recurrence check derived from it: the memory it consolidated and its buffer rows.

The check runs when a session ends, so the manager is given the chat the summary came from. Each case drives real
managers over SQLite and one embedded Qdrant: the buffer rows, the consolidated memory and the purge are all
observed in the store, where a mock would accept any call.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.recurrence import buffer_collection
from myrm_agent_harness.toolkits.memory.types import SemanticMemory
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore
from tests.support.consolidation_seeds import NewManager

TOPIC = "How do I keep flaky pytest tests under control with retries and logging"
CHATS = ("chat-1", "chat-2", "chat-3", "chat-4")


async def run_sessions(manager: MemoryManager, chats: tuple[str, ...]) -> None:
    for chat in chats:
        await manager.check_session_recurrence(TOPIC, source_chat_id=chat)


async def memory_of(manager: MemoryManager, chat_id: str) -> SemanticMemory:
    """The one semantic memory written from ``chat_id``."""
    [memory_id] = (await manager.list_memory_ids_by_metadata("source_chat_id", chat_id))["semantic"]
    memory = await manager.get_memory(memory_id)
    assert isinstance(memory, SemanticMemory)
    return memory


async def buffer_rows(qdrant: QdrantVectorStore, manager: MemoryManager) -> list[tuple[str, str]]:
    """(owner, chat) of every row in the buffer in a stable order; the chat is empty for a row with no chat link."""
    docs, _ = await qdrant.scroll(buffer_collection(manager.config.collection_prefix), limit=100)
    return sorted((str(doc.metadata["user_id"]), str(doc.metadata.get("source_chat_id", ""))) for doc in docs)


async def test_a_consolidated_memory_derives_from_every_chat_that_fed_it(new_manager: NewManager) -> None:
    manager = new_manager()

    await run_sessions(manager, CHATS)

    memory = await memory_of(manager, "chat-4")
    assert memory.content == TOPIC
    assert sorted(memory.source_chat_ids) == list(CHATS)


async def test_deleting_one_feeding_chat_removes_the_memory_and_only_its_own_rows(
    new_manager: NewManager, qdrant: QdrantVectorStore
) -> None:
    manager = new_manager()
    await run_sessions(manager, CHATS)
    assert await manager.count_by_source_chat_id("chat-2") == {"semantic": 1}

    purged = await manager.purge_by_source_chat_id("chat-2")

    assert purged["semantic"] == 1
    assert await manager.count_by_source_chat_id("chat-4") == {}
    assert await buffer_rows(qdrant, manager) == [("u1", "chat-1"), ("u1", "chat-3"), ("u1", "chat-4")]


async def test_a_must_remember_summary_is_stored_from_its_one_chat(new_manager: NewManager) -> None:
    manager = new_manager()

    await manager.check_session_recurrence("I have a severe allergy to penicillin", source_chat_id="chat-a")

    memory = await memory_of(manager, "chat-a")
    assert memory.source_chat_ids == []
    await manager.purge_by_source_chat_id("chat-a")
    assert await manager.count_by_source_chat_id("chat-a") == {}


async def test_deleting_a_chat_clears_its_buffer_rows_even_when_detection_is_off(
    new_manager: NewManager, qdrant: QdrantVectorStore
) -> None:
    manager = new_manager()
    await manager.check_session_recurrence(TOPIC, source_chat_id="chat-a")
    manager._recurrence_detector = None

    await manager.purge_by_source_chat_id("chat-a")

    assert await buffer_rows(qdrant, manager) == []


async def test_erasing_everything_clears_the_buffer_rows_of_that_user_only(
    new_manager: NewManager, qdrant: QdrantVectorStore
) -> None:
    mine, theirs = new_manager(), new_manager(user_id="u2")
    await mine.check_session_recurrence(TOPIC, source_chat_id="chat-a")
    await theirs.check_session_recurrence(TOPIC, source_chat_id="chat-b")

    await mine.delete_all()

    assert await buffer_rows(qdrant, mine) == [("u2", "chat-b")]


async def test_a_manager_consolidates_only_its_own_users_and_scopes_sessions(new_manager: NewManager) -> None:
    mine, other_user, other_scope = new_manager(), new_manager(user_id="u2"), new_manager(["agent:x"])
    for other in (other_user, other_scope):
        await run_sessions(other, ("theirs-1", "theirs-2", "theirs-3"))

    await mine.check_session_recurrence(TOPIC, source_chat_id="mine-1")
    assert await mine.count_by_source_chat_id("mine-1") == {}

    await run_sessions(mine, ("mine-2", "mine-3", "mine-4"))
    assert sorted((await memory_of(mine, "mine-4")).source_chat_ids) == ["mine-1", "mine-2", "mine-3", "mine-4"]
