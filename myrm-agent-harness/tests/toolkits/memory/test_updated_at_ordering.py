"""Listing by ``updated_at`` follows the latest write of a memory, not its first.

The store orders on a payload copy of the timestamp. A memory read back and written again used to carry the copy it
was read with, so the copy stayed at the first write and a memory edited last sorted as if it had never been edited.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import AnyMemory, MemoryType, SemanticMemory
from tests.support.consolidation_seeds import NewManager, seed, semantic


async def seeded_pair(manager: MemoryManager) -> tuple[SemanticMemory, SemanticMemory]:
    """Two memories, the first written earlier than the second."""
    older, newer = semantic("User drinks green tea", 1), semantic("User rides a bicycle to work", 2)
    await seed(manager, [older, newer])
    return older, newer


async def listed_newest_first(manager: MemoryManager) -> list[AnyMemory]:
    return await manager.list_memories(MemoryType.SEMANTIC, limit=2, sort_by="updated_at")


async def test_an_importance_edit_moves_the_memory_first(new_manager: NewManager) -> None:
    manager = new_manager()
    older, newer = await seeded_pair(manager)

    await manager.update_memory(older.id, importance=0.9)

    assert [memory.id for memory in await listed_newest_first(manager)] == [older.id, newer.id]


async def test_a_content_edit_moves_the_memory_first(new_manager: NewManager) -> None:
    manager = new_manager()
    older, newer = await seeded_pair(manager)

    await manager.update_memory(older.id, content="User drinks oolong")

    assert [memory.id for memory in await listed_newest_first(manager)] == [older.id, newer.id]


async def test_the_stores_timestamp_copies_are_not_handed_out_as_metadata(new_manager: NewManager) -> None:
    manager = new_manager()
    older, _ = await seeded_pair(manager)
    await manager.update_memory(older.id, importance=0.9)

    memories = [*await listed_newest_first(manager), await manager.get_memory(older.id)]

    assert all(memory is not None and memory.metadata == {} for memory in memories)
