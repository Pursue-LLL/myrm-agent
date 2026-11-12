"""What a consolidation cycle writes derives from the chats of the memories it read, so deleting one of them reaches it.

Each case drives a real manager over SQLite and an embedded Qdrant through run_consolidation, the call the idle worker
makes: the memory a merge creates, the counterpart a contested correction keeps beside the original, and the insights
a cycle draws from each namespace group.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation import run_consolidation
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATION_INSIGHT_TAG,
    ConsolidationResponse,
)
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory
from tests.support.consolidation_cycles import CONFIG, TEA, TEA_TOO, correct, merge, run_cycle, stored_insights
from tests.support.consolidation_seeds import NewManager, llm_answering_after, seed, semantic

SHARED = ["chat-b", "chat-a"]
INSIGHT = "User keeps calm daily routines around tea and books"


async def stored(manager: MemoryManager, memory_id: str) -> SemanticMemory:
    memory = await manager.get_memory(memory_id)
    assert isinstance(memory, SemanticMemory)
    return memory


async def test_a_merged_memory_derives_from_every_chat_of_its_sources(new_manager: NewManager) -> None:
    manager = new_manager()
    first = semantic(TEA, 1, source_chat_id="chat-a")
    second = semantic(TEA_TOO, 2, source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-c"])
    await seed(manager, [first, second])

    stats = await run_cycle(manager, merge(first, second, TEA))

    [merged_id] = stats.undo.created
    merged = await stored(manager, merged_id)
    assert merged.source_chat_id == "chat-b"
    assert sorted(merged.source_chat_ids) == ["chat-a", "chat-b", "chat-c"]
    await manager.purge_by_source_chat_id("chat-c")
    assert await manager.get_memory(merged_id) is None
    assert await manager.get_memory(first.id) is not None


async def test_a_merge_is_skipped_when_a_source_chat_is_deleted_while_the_model_thinks(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    first = semantic(TEA, 1, source_chat_id="chat-a")
    second = semantic(TEA_TOO, 2, source_chat_id="chat-b")
    await seed(manager, [first, second])
    response = ConsolidationResponse(operations=[merge(first, second, TEA)])

    async def delete_chat_b_then_answer(_messages: object) -> ConsolidationResponse:
        await manager.purge_by_source_chat_id("chat-b")
        return response

    structured = AsyncMock()
    structured.ainvoke = AsyncMock(side_effect=delete_chat_b_then_answer)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    stats = await run_consolidation(manager, llm, CONFIG)

    assert (stats.merged, stats.undo.created) == (0, [])
    assert [memory.id for memory in await manager.list_memories(MemoryType.SEMANTIC)] == [first.id]
    assert (await stored(manager, first.id)).importance == first.importance


async def test_a_contested_correction_keeps_the_lineage_of_the_memory_it_contests(new_manager: NewManager) -> None:
    manager = new_manager()
    old = semantic("User works on macOS", 1, source_chat_id="chat-b", source_chat_ids=SHARED)
    await seed(manager, [old, semantic("User likes dark mode", 2, source_chat_id="chat-c")])

    stats = await run_cycle(manager, correct(old, "User works on Linux"))

    assert (stats.updated, stats.corrected) == (1, 0)
    [counterpart_id] = stats.undo.created
    counterpart = await stored(manager, counterpart_id)
    assert counterpart.content == "User works on Linux"
    assert (counterpart.source_chat_id, counterpart.source_chat_ids) == ("chat-b", SHARED)
    await manager.purge_by_source_chat_id("chat-a")
    assert await manager.get_memory(counterpart_id) is None
    assert await manager.get_memory(old.id) is None


async def test_an_insight_derives_from_every_chat_of_the_group_it_was_drawn_from(new_manager: NewManager) -> None:
    manager = new_manager()
    await seed(
        manager,
        [
            semantic(TEA, 1, source_chat_id="chat-a"),
            semantic("User reads before bed", 2, source_chat_id="chat-b", source_chat_ids=["chat-b", "chat-d"]),
            semantic("User has no chat link", 3),
        ],
    )

    stats = await run_cycle(manager, insights=(INSIGHT,))

    [insight] = await stored_insights(manager)
    assert stats.insights == (INSIGHT,)
    assert insight.content == INSIGHT and CONSOLIDATION_INSIGHT_TAG in insight.tags
    assert insight.source_chat_id == "chat-b"
    assert sorted(insight.source_chat_ids) == ["chat-a", "chat-b", "chat-d"]
    await manager.purge_by_source_chat_id("chat-d")
    assert await manager.get_memory(insight.id) is None


async def test_an_insight_the_deleted_chat_fence_refuses_is_not_reported_as_stored(new_manager: NewManager) -> None:
    manager = new_manager()
    await seed(manager, [semantic(TEA, 1, source_chat_id="chat-a"), semantic(TEA_TOO, 2, source_chat_id="chat-b")])
    llm = llm_answering_after(
        ConsolidationResponse(insights=[INSIGHT]), lambda: manager.purge_by_source_chat_id("chat-b")
    )
    on_complete = AsyncMock()

    stats = await run_consolidation(manager, llm, CONFIG, on_complete=on_complete)

    assert stats.insights == ()
    on_complete.assert_awaited_once_with(stats)
    assert await stored_insights(manager) == []
