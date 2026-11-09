"""What the consolidation undo promises while someone else acts: a project's manager and a second click on the card.

Each case drives real managers over one SQLite file and one set of collections, because the promises are about what
the shared stores hold afterwards: a manager that owns another namespace must neither see nor undo this one's cycle,
and two undo calls for the same cycle, from two tabs or two devices, must leave the memories as one call would.
"""

from __future__ import annotations

import asyncio

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import get_undo_summary, undo_last_consolidation
from myrm_agent_harness.toolkits.memory.types import AnyMemory
from tests.support.consolidation_cycles import TEA, TEA_TOO, merge, merged_pair, run_cycle
from tests.support.consolidation_seeds import NewManager, seed, semantic


async def held(manager: MemoryManager, memory: AnyMemory) -> tuple[object, ...] | None:
    """What a cycle can change of a memory: its text, ratings, status and metadata."""
    current = await manager.get_memory(memory.id)
    if current is None:
        return None
    return (current.content, current.importance, getattr(current, "confidence", None), current.status, current.metadata)


async def test_a_project_manager_neither_sees_nor_undoes_the_global_managers_cycle(new_manager: NewManager) -> None:
    owner, project = new_manager(), new_manager(["project:alpha", "global"])
    _, _, merged_id = await merged_pair(owner)
    summary = await get_undo_summary(owner)
    assert summary is not None

    assert await get_undo_summary(project) is None
    assert await undo_last_consolidation(project, summary.cycle_id) is None

    assert await owner.get_memory(merged_id) is not None
    assert await get_undo_summary(owner) == summary


async def test_two_undo_calls_for_one_cycle_leave_the_memories_as_one_call_would(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    before = [await held(manager, memory) for memory in (first, second)]
    stats = await run_cycle(manager, merge(first, second, TEA))
    [merged_id] = stats.undo.created
    summary = await get_undo_summary(manager)
    assert summary is not None

    results = await asyncio.gather(
        undo_last_consolidation(manager, summary.cycle_id), undo_last_consolidation(manager, summary.cycle_id)
    )

    assert all(result is not None and result.errors == 0 for result in results)
    assert [await held(manager, memory) for memory in (first, second)] == before
    assert await manager.get_memory(merged_id) is None
    assert await get_undo_summary(manager) is None
