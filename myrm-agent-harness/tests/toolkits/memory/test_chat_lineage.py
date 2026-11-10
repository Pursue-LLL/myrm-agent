"""A memory derived from several chats belongs to each of them: the link survives every rewrite and a chat purge reaches it.

Real manager over an embedded Qdrant and SQLite. Memories are laid out below the manager so each chat link is exact.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, MemoryType, SemanticMemory
from tests.support.consolidation_seeds import NewManager, episodic, seed, semantic

# Chat b is the latest source of a memory that was also drawn from chat a.
SHARED = ["chat-b", "chat-a"]


async def stored(manager: MemoryManager, memory_id: str) -> SemanticMemory | EpisodicMemory:
    memory = await manager.get_memory(memory_id)
    assert isinstance(memory, SemanticMemory | EpisodicMemory)
    return memory


async def test_lineage_survives_the_store_and_a_rewrite(new_manager: NewManager) -> None:
    manager = new_manager()
    note = semantic("User drinks green tea every morning", 1, source_chat_id="chat-b", source_chat_ids=SHARED)
    event = episodic("User asked about tea", 2, source_chat_id="chat-b", source_chat_ids=SHARED)
    await seed(manager, [note, event])

    await manager.update_memory(note.id, content="User drinks oolong tea every morning")
    await manager.update_memory(event.id, importance=0.9)

    for memory_id in (note.id, event.id):
        memory = await stored(manager, memory_id)
        assert (memory.source_chat_id, memory.source_chat_ids) == ("chat-b", SHARED)


async def test_export_and_import_keep_the_lineage(new_manager: NewManager) -> None:
    manager = new_manager()
    await seed(
        manager,
        [semantic("User drinks green tea every morning", 1, source_chat_id="chat-b", source_chat_ids=SHARED)],
    )

    exported = await manager.export_all()
    await manager.delete_all()
    await manager.import_memories(exported, skip_duplicates=False)

    [restored] = await manager.list_memories(MemoryType.SEMANTIC)
    assert isinstance(restored, SemanticMemory)
    assert (restored.source_chat_id, restored.source_chat_ids) == ("chat-b", SHARED)


async def test_purging_a_chat_removes_every_memory_derived_from_it(new_manager: NewManager) -> None:
    manager = new_manager()
    told_in_a = semantic("fact told in chat a", 1, source_chat_id="chat-a")
    # Matches the purge through both of its links: it still counts once.
    latest_in_a = semantic(
        "fact whose latest source is chat a", 2, source_chat_id="chat-a", source_chat_ids=SHARED[::-1]
    )
    drawn_from_a = semantic("fact whose latest source is chat b", 3, source_chat_id="chat-b", source_chat_ids=SHARED)
    event_from_a = episodic(
        "event drawn from chats c and a", 4, source_chat_id="chat-c", source_chat_ids=["chat-c", "chat-a"]
    )
    told_in_c = semantic("fact told in chat c", 5, source_chat_id="chat-c")
    await seed(manager, [told_in_a, latest_in_a, drawn_from_a, event_from_a, told_in_c])

    preview = await manager.count_by_source_chat_id("chat-a")
    purged = await manager.purge_by_source_chat_id("chat-a")

    assert preview == {"semantic": 3, "episodic": 1}
    assert {kind: count for kind, count in purged.items() if count} == preview
    assert [memory.id for memory in await manager.list_memories(MemoryType.SEMANTIC)] == [told_in_c.id]
    assert await manager.list_memories(MemoryType.EPISODIC) == []


async def test_purging_a_chat_leaves_memories_of_other_chats(new_manager: NewManager) -> None:
    manager = new_manager()
    drawn_from_a_and_b = semantic("fact drawn from chats a and b", 1, source_chat_id="chat-b", source_chat_ids=SHARED)
    await seed(manager, [drawn_from_a_and_b, semantic("fact told in chat c", 2, source_chat_id="chat-c")])

    assert await manager.count_by_source_chat_id("chat-z") == {}
    assert {kind: count for kind, count in (await manager.purge_by_source_chat_id("chat-z")).items() if count} == {}
    assert len(await manager.list_memories(MemoryType.SEMANTIC)) == 2


async def test_a_correction_inherits_the_lineage_of_the_memory_it_corrects(new_manager: NewManager) -> None:
    manager = new_manager()
    wrong = semantic("User lives in Paris", 1, source_chat_id="chat-b", source_chat_ids=SHARED)
    await seed(manager, [wrong])

    correction = await manager.correct_memory(wrong.id, "User lives in Lyon")

    memory = await stored(manager, correction.id)
    assert (memory.source_chat_id, memory.source_chat_ids) == ("chat-b", SHARED)
    await manager.purge_by_source_chat_id("chat-a")
    assert await manager.get_memory(correction.id) is None
