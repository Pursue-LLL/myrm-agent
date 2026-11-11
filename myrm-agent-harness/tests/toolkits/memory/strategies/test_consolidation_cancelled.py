"""A consolidation cycle the idle worker cancels is never left half applied.

The worker cancels a running cycle when the user's next turn ends. Each case delivers a real ``task.cancel()`` to a
``run_consolidation`` task over a real manager (SQLite and an embedded Qdrant). Cancelled while the cycle writes, it
still finishes, journals itself and advances its stamp; cancelled before the model has answered, it has written nothing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies import consolidation
from myrm_agent_harness.toolkits.memory.strategies.consolidation import get_last_consolidated_at, run_consolidation
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATION_SOURCE_KEY,
    ConsolidationResponse,
    ConsolidationStats,
    MergeOp,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import UndoResult, get_undo_summary
from myrm_agent_harness.toolkits.memory.types import AnyMemory, MemoryType, SemanticMemory
from tests.support.consolidation_cycles import CONFIG, TEA, TEA_TOO, merge, run_cycle, undo
from tests.support.consolidation_seeds import NewManager, llm_returning, seed, semantic

PAIRS = (
    (TEA, TEA_TOO, "User drinks green tea in the morning"),
    ("User keeps a standing desk", "User works at a sit-stand desk", "User works at a standing desk"),
    ("User rides a bicycle to work", "User cycles to the office daily", "User cycles to work every day"),
)
# A merge demotes its two sources, so the third update of a cycle is the first one of its second merge.
SECOND_MERGE_BEGINS = 3


async def seed_pairs(manager: MemoryManager) -> list[SemanticMemory]:
    memories: list[SemanticMemory] = []
    for index, (first, second, _) in enumerate(PAIRS):
        memories += [semantic(first, 2 * index + 1, importance=0.4), semantic(second, 2 * index + 2, importance=0.9)]
    await seed(manager, memories)
    return memories


def merges(memories: Sequence[SemanticMemory]) -> list[MergeOp]:
    return [merge(memories[2 * i], memories[2 * i + 1], merged) for i, (_, _, merged) in enumerate(PAIRS)]


async def merge_products(manager: MemoryManager) -> list[AnyMemory]:
    memories = await manager.list_memories(MemoryType.SEMANTIC)
    return [memory for memory in memories if CONSOLIDATION_SOURCE_KEY in memory.metadata]


def start_cycle(manager: MemoryManager, memories: Sequence[SemanticMemory]) -> asyncio.Task[ConsolidationStats]:
    response = ConsolidationResponse(operations=merges(memories))
    return asyncio.create_task(run_consolidation(manager, llm_returning(response), CONFIG))


async def cancel_when_update_begins(
    monkeypatch: pytest.MonkeyPatch, cycle: asyncio.Task[ConsolidationStats], number: int
) -> None:
    """Cancel ``cycle`` as its ``number``-th memory update begins; that update itself then runs on."""
    update_memory = MemoryManager.update_memory
    updates = 0

    async def update(self: MemoryManager, memory_id: str, **fields: object) -> AnyMemory:
        nonlocal updates
        updates += 1
        if updates == number:
            cycle.cancel()
            await asyncio.sleep(0)  # a cycle that is not shielded receives the cancel right here
        return await update_memory(self, memory_id, **fields)

    monkeypatch.setattr(MemoryManager, "update_memory", update)
    with pytest.raises(asyncio.CancelledError):
        await cycle


async def wait_until_stamped(manager: MemoryManager) -> None:
    """The stamp is the last write of a cycle, so once it has moved the cycle's journal is saved as well."""
    async with asyncio.timeout(10):
        while await get_last_consolidated_at(manager) is None:
            await asyncio.sleep(0.01)


async def cycle_cancelled_mid_write(manager: MemoryManager, monkeypatch: pytest.MonkeyPatch) -> list[SemanticMemory]:
    memories = await seed_pairs(manager)
    await cancel_when_update_begins(monkeypatch, start_cycle(manager, memories), SECOND_MERGE_BEGINS)
    await wait_until_stamped(manager)
    return memories


async def test_a_cycle_cancelled_while_it_writes_still_finishes_and_can_be_undone(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()

    memories = await cycle_cancelled_mid_write(manager, monkeypatch)

    summary = await get_undo_summary(manager)
    assert summary is not None and (summary.merged, summary.change_count) == (3, 9)
    assert len(await merge_products(manager)) == 3
    assert await undo(manager) == UndoResult(rolled_back=9)
    assert await merge_products(manager) == []
    for source in memories:
        restored = await manager.get_memory(source.id)
        assert restored is not None
        assert (restored.importance, "consolidated" in restored.metadata) == (source.importance, False)


async def test_the_next_cycle_does_not_merge_what_a_cancelled_cycle_already_merged(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    memories = await cycle_cancelled_mid_write(manager, monkeypatch)

    await run_cycle(manager, *merges(memories))

    assert len(await merge_products(manager)) == 3


async def test_a_cycle_cancelled_before_the_model_answers_writes_nothing(new_manager: NewManager) -> None:
    manager = new_manager()
    memories = await seed_pairs(manager)
    asked = asyncio.Event()

    async def never_answers(_messages: object) -> ConsolidationResponse:
        asked.set()
        return await asyncio.Future[ConsolidationResponse]()

    structured = AsyncMock()
    structured.ainvoke = AsyncMock(side_effect=never_answers)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    cycle = asyncio.create_task(run_consolidation(manager, llm, CONFIG))
    await asked.wait()

    cycle.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cycle

    assert await get_undo_summary(manager) is None
    assert await get_last_consolidated_at(manager) is None
    assert len(await manager.list_memories(MemoryType.SEMANTIC)) == len(memories)


async def test_a_failure_after_the_cancel_is_logged_because_nobody_is_left_to_see_it(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    manager = new_manager()
    cycle = start_cycle(manager, await seed_pairs(manager))

    async def fails_after_the_cancel(*_args: object, **_kwargs: object) -> ConsolidationStats:
        cycle.cancel()
        await asyncio.sleep(0)
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(consolidation, "execute_operations", fails_after_the_cancel)
    caplog.set_level(logging.ERROR, logger=consolidation.logger.name)
    with pytest.raises(asyncio.CancelledError):
        await cycle

    async with asyncio.timeout(10):
        while "failed after its caller was cancelled" not in caplog.text:
            await asyncio.sleep(0.01)
    assert "store unavailable" in caplog.text
