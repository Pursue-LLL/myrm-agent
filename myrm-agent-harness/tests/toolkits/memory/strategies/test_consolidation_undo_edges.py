"""What the consolidation undo promises when a write fails, when another writer acts, after a restart and for any mix.

The golden path is covered next to it. Each case here drives a real manager over SQLite and an embedded Qdrant, because
the promises are about what the stores hold afterwards: a failed write must not stop the rest, a newer cycle's journal
must outlive the undo that ran beside it, a recall must not read as a user edit, and whatever mix of operations a
cycle performed, undoing it must give every memory back exactly as it was.
"""

from __future__ import annotations

import asyncio
import logging
import random
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies import consolidation_undo
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    ConsolidationOp,
    ConsolidationStats,
    PreImage,
    UndoJournal,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import (
    CycleWrites,
    UndoResult,
    get_undo_summary,
    save_undo,
    undo_last_consolidation,
)
from myrm_agent_harness.toolkits.memory.strategies.merger import (
    DeterministicThreeStateMerger,
    MergeDecision,
    MergeState,
)
from myrm_agent_harness.toolkits.memory.types import AnyMemory, MemoryStatus, SemanticMemory
from tests.support.consolidation_cycles import (
    TEA,
    TEA_TOO,
    correct,
    merge,
    merged_pair,
    rewrite,
    run_cycle,
    store_fresh,
    undo,
)
from tests.support.consolidation_manager import make_manager
from tests.support.consolidation_seeds import NewManager, episodic, seed, semantic

HABITS = (
    "drinks green tea",
    "rides a bicycle to work",
    "keeps a standing desk",
    "reads before sleeping",
    "waters the balcony herbs",
    "plays chess on weekends",
    "cooks pasta on Sundays",
    "walks the dog at dawn",
)


async def fingerprint(manager: MemoryManager, memory_id: str) -> dict[str, object] | None:
    """Everything the store persists of a memory except when it was last written.

    An episodic memory's ``timestamp`` is a default taken on every read and never stored.
    """
    memory = await manager.get_memory(memory_id)
    return None if memory is None else memory.model_dump(exclude={"updated_at", "timestamp"})


def changed_fields(
    before: dict[str, object] | None, after: dict[str, object] | None
) -> dict[str, tuple[object, object]]:
    """The fields that differ between two fingerprints, as ``{field: (before, after)}``.

    The store re-normalises a vector on every upsert, which moves its float32 components by one ulp, so embeddings
    are compared within a tolerance.
    """
    if before is None or after is None:
        return {} if before == after else {"present": (before is not None, after is not None)}

    def same(key: str) -> bool:
        return before[key] == (pytest.approx(after[key], abs=1e-6) if key == "embedding" else after[key])

    return {key: (before[key], after[key]) for key in before if not same(key)}


async def test_a_cycle_whose_journal_cannot_be_saved_still_completes(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1), semantic(TEA_TOO, 2)
    await seed(manager, [first, second])

    async def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(consolidation_undo, "write_bookkeeping", refuse)
    with caplog.at_level(logging.WARNING, logger=consolidation_undo.logger.name):
        stats = await run_cycle(manager, merge(first, second, TEA))

    assert stats.merged == 1
    assert "Failed to save the consolidation undo journal" in caplog.text
    assert await get_undo_summary(manager) is None


async def test_a_manager_without_a_relational_store_has_nothing_to_journal() -> None:
    manager = make_manager()
    manager.has_relational = False

    await save_undo(manager, ConsolidationStats(updated=1, undo=UndoJournal(created=["new-id"])))

    assert await get_undo_summary(manager) is None
    assert await undo_last_consolidation(manager, "any") is None
    manager._rel.assert_not_called()


async def test_a_delete_that_fails_is_reported_and_the_rest_is_still_restored(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    _, second, merged_id = await merged_pair(manager)
    summary = await get_undo_summary(manager)
    assert summary is not None
    monkeypatch.setattr(MemoryManager, "delete_memory", AsyncMock(side_effect=RuntimeError("store unavailable")))

    result = await undo_last_consolidation(manager, summary.cycle_id)

    assert result == UndoResult(rolled_back=2, errors=1)
    assert await manager.get_memory(merged_id) is not None
    restored = await manager.get_memory(second.id)
    assert restored is not None and restored.importance == 0.9
    assert await get_undo_summary(manager) is None  # the slot is consumed whatever the outcome


async def test_a_restore_that_fails_is_reported_and_the_rest_is_still_restored(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    first, second, merged_id = await merged_pair(manager)
    summary = await get_undo_summary(manager)
    assert summary is not None
    update_memory = MemoryManager.update_memory

    async def refuse_the_first_source(self: MemoryManager, memory_id: str, **fields: object) -> AnyMemory:
        if memory_id == first.id:
            raise RuntimeError("write failed")
        return await update_memory(self, memory_id, **fields)

    monkeypatch.setattr(MemoryManager, "update_memory", refuse_the_first_source)

    result = await undo_last_consolidation(manager, summary.cycle_id)

    assert result == UndoResult(rolled_back=2, errors=1)
    assert await manager.get_memory(merged_id) is None
    restored = await manager.get_memory(second.id)
    assert restored is not None and restored.importance == 0.9
    assert await get_undo_summary(manager) is None


async def test_undoing_does_not_take_a_newer_cycles_journal_with_it(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    await merged_pair(manager)
    desk = semantic("User keeps a standing desk", 3, importance=0.6)
    await seed(manager, [desk])
    summary = await get_undo_summary(manager)
    assert summary is not None
    newer = ConsolidationStats(
        updated=1,
        undo=UndoJournal(
            touched={desk.id: PreImage(importance=0.6, confidence=1.0, status=MemoryStatus.ACTIVE, metadata_keys=[])}
        ),
    )
    update_memory = MemoryManager.update_memory
    newer_saved = False

    async def update_while_a_newer_cycle_saves(self: MemoryManager, memory_id: str, **fields: object) -> AnyMemory:
        nonlocal newer_saved
        if not newer_saved:
            newer_saved = True
            await save_undo(manager, newer)
        return await update_memory(self, memory_id, **fields)

    monkeypatch.setattr(MemoryManager, "update_memory", update_while_a_newer_cycle_saves)

    assert await undo_last_consolidation(manager, summary.cycle_id) == UndoResult(rolled_back=3)

    after = await get_undo_summary(manager)
    assert after is not None and after.cycle_id != summary.cycle_id and after.change_count == 1


async def test_a_cycle_cut_short_leaves_the_earlier_undo_intact(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    first, second, merged_id = await merged_pair(manager)
    earlier = await get_undo_summary(manager)
    desk, bike = await store_fresh(manager, "User keeps a standing desk", "User rides a bicycle to work")
    update_memory = MemoryManager.update_memory
    writes = 0

    async def cancelled_on_the_second_write(self: MemoryManager, memory_id: str, **fields: object) -> AnyMemory:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise asyncio.CancelledError
        return await update_memory(self, memory_id, **fields)

    monkeypatch.setattr(MemoryManager, "update_memory", cancelled_on_the_second_write)
    with pytest.raises(asyncio.CancelledError):
        await run_cycle(manager, rewrite(desk, "User keeps a sit-stand desk", 0.7), rewrite(bike, "User cycles", 0.7))
    monkeypatch.undo()

    assert earlier is not None and await get_undo_summary(manager) == earlier
    assert await undo(manager) == UndoResult(rolled_back=3)
    assert await manager.get_memory(merged_id) is None
    for restored, importance in ((first, 0.4), (second, 0.9)):
        memory = await manager.get_memory(restored.id)
        assert memory is not None and memory.importance == importance
    untouched = await manager.get_memory(bike.id)
    assert untouched is not None and untouched.content == bike.content


async def test_memories_the_user_deleted_after_the_cycle_are_skipped_and_the_rest_is_restored(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    first, second, merged_id = await merged_pair(manager)
    collection = manager.config.semantic_collection
    await manager.delete_memory(collection, [merged_id])
    await manager.delete_memory(collection, [first.id])

    summary = await get_undo_summary(manager)

    assert summary is not None and (summary.change_count, summary.conflict_count) == (3, 2)
    assert await undo_last_consolidation(manager, summary.cycle_id) == UndoResult(rolled_back=1, skipped_conflict=2)
    assert await manager.get_memory(merged_id) is None and await manager.get_memory(first.id) is None
    restored = await manager.get_memory(second.id)
    assert restored is not None and restored.importance == 0.9


async def test_the_undo_gives_back_the_status_a_memory_had_when_the_cycle_first_wrote_to_it(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    memory = semantic(TEA, 1, importance=0.4)
    await seed(manager, [memory])
    await manager.update_memory(memory.id, status=MemoryStatus.DISABLED)
    stats = ConsolidationStats()

    await CycleWrites(manager, stats.undo).update_memory(memory.id, importance=0.05)
    await save_undo(manager, stats)

    assert await undo(manager) == UndoResult(rolled_back=1)
    restored = await manager.get_memory(memory.id)
    assert restored is not None and (restored.status, restored.importance) == (MemoryStatus.DISABLED, 0.4)


async def test_the_undo_survives_a_restart(new_manager: NewManager) -> None:
    manager = new_manager()
    _, _, merged_id = await merged_pair(manager)

    restarted = new_manager()

    assert await undo(restarted) == UndoResult(rolled_back=3)
    assert await manager.get_memory(merged_id) is None


async def test_recalling_the_changed_memories_is_not_a_user_edit(new_manager: NewManager) -> None:
    manager = new_manager()
    _, _, merged_id = await merged_pair(manager)

    await manager.search("green tea", limit=10)
    await asyncio.gather(*(task for task in asyncio.all_tasks() if task.get_name() == "bump_access_counts"))

    recalled = await manager.get_memory(merged_id)
    assert recalled is not None and recalled.access_count == 1  # the recall was recorded
    summary = await get_undo_summary(manager)
    assert summary is not None and summary.conflict_count == 0
    assert await undo(manager) == UndoResult(rolled_back=3)


async def test_a_store_that_hands_back_an_existing_memory_is_not_journaled_as_created(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = new_manager()
    existing = semantic(TEA, 1)
    await seed(manager, [existing])
    monkeypatch.setattr(MemoryManager, "store", AsyncMock(return_value=existing))
    journal = UndoJournal()

    await CycleWrites(manager, journal).store(SemanticMemory(content=TEA))

    assert journal.created == []


async def test_undoing_a_cycle_restores_episodic_memories_too(new_manager: NewManager) -> None:
    manager = new_manager()
    lesson, workshop = episodic("User attended a pottery class", 1), episodic("User joined a pottery workshop", 2)
    await seed(manager, [lesson, workshop])
    before = [await fingerprint(manager, memory.id) for memory in (lesson, workshop)]

    stats = await run_cycle(manager, merge(lesson, workshop, "User took pottery classes"))

    assert stats.merged == 1
    assert await fingerprint(manager, lesson.id) != before[0]
    assert await undo(manager) == UndoResult(rolled_back=3)
    for memory, original in zip((lesson, workshop), before, strict=True):
        assert changed_fields(original, await fingerprint(manager, memory.id)) == {}


def random_memories(rng: random.Random) -> list[AnyMemory]:
    """Eight memories of both kinds, with importance, confidence and metadata drawn at the edges and between."""
    memories: list[AnyMemory] = []
    for index, habit in enumerate(HABITS, start=1):
        if rng.random() < 0.25:
            memories.append(episodic(f"User {habit}", index))
            continue
        memories.append(
            semantic(
                f"User {habit}",
                index,
                importance=rng.choice([0.0, 0.2, 0.5, 0.8, 1.0]),
                confidence=rng.choice([0.1, 0.5, 0.9, 1.0]),
                metadata={"origin": rng.choice(["chat", "import"])} if rng.random() < 0.5 else {},
            )
        )
    return memories


def random_operations(rng: random.Random, memories: list[AnyMemory]) -> list[ConsolidationOp]:
    """At least one merge, correction or rewrite over disjoint memories; some memories are left alone."""
    pool = rng.sample(memories, k=len(memories))
    operations: list[ConsolidationOp] = []
    while pool and (not operations or rng.random() > 0.15):
        kind = rng.choice(["merge", "correct", "rewrite"])
        target = pool.pop()
        if kind == "merge" and pool:
            other = pool.pop()
            operations.append(merge(target, other, f"{target.content}; {other.content}"))
        elif kind == "correct":
            operations.append(correct(target, f"{target.content} (corrected)"))
        else:
            operations.append(rewrite(target, f"{target.content} (updated)", rng.choice([0.3, 0.6, 0.9])))
    return operations


@pytest.mark.parametrize("case", range(12))
async def test_undoing_any_mix_of_operations_puts_every_memory_back_exactly(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch, case: int
) -> None:
    rng = random.Random(case)

    def decide(self: DeterministicThreeStateMerger, *, existing: AnyMemory, **_: object) -> MergeDecision:
        state = rng.choice([MergeState.CONFIRM, MergeState.SUPPLEMENT, MergeState.CONFLICT, MergeState.NEW])
        return MergeDecision(
            state=state,
            merged_content=f"{existing.content} and more",
            updated_confidence=round(rng.uniform(0.1, 0.9), 2),
            candidate_confidence=0.35,
        )

    monkeypatch.setattr(DeterministicThreeStateMerger, "evaluate", decide)
    manager = new_manager()
    memories = random_memories(rng)
    await seed(manager, memories)
    before = {memory.id: await fingerprint(manager, memory.id) for memory in memories}

    stats = await run_cycle(manager, *random_operations(rng, memories))

    assert stats.undo.change_count > 0
    # The cycle did change something, so putting everything back is not the trivial case.
    assert any([changed_fields(before[m.id], await fingerprint(manager, m.id)) for m in memories])
    assert await undo(manager) == UndoResult(rolled_back=stats.undo.change_count)
    for memory in memories:
        assert changed_fields(before[memory.id], await fingerprint(manager, memory.id)) == {}
    for created_id in stats.undo.created:
        assert await manager.get_memory(created_id) is None
