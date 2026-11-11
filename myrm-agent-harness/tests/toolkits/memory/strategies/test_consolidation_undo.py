"""A consolidation cycle can be undone exactly, because what it changes is journaled as it happens.

A mock manager cannot show that a restored memory is the memory the cycle found: the values a write replaced, the keys
it added, an archive that landed after it and a user edit that landed after that. Each case drives a real manager over
SQLite and an embedded Qdrant through run_consolidation, the call the idle worker makes.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.memory._internal.maintenance import run_forgetting
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.bookkeeping import write_bookkeeping
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import UndoJournal, UpdateContentOp
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import (
    _UNDO_KEY,
    CycleWrites,
    UndoResult,
    get_undo_summary,
    undo_last_consolidation,
)
from myrm_agent_harness.toolkits.memory.strategies.merger import (
    DeterministicThreeStateMerger,
    MergeDecision,
    MergeState,
)
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, SemanticMemory
from tests.support.consolidation_cycles import (
    TEA,
    TEA_TOO,
    correct,
    merge,
    merged_pair,
    rewrite,
    run_cycle,
    store_fresh,
    stored_insights,
    undo,
)
from tests.support.consolidation_seeds import NewManager, seed, semantic


async def snapshot(manager: MemoryManager, memory: SemanticMemory) -> tuple[object, ...]:
    """Every field an undo has to put back, as the store holds them."""
    current = await manager.get_memory(memory.id)
    assert isinstance(current, SemanticMemory)
    return (current.content, current.importance, current.confidence, current.status, current.metadata)


async def test_undoing_a_merge_deletes_the_merged_memory_and_restores_each_source_exactly(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    first = semantic(TEA, 1, importance=0.4, metadata={"source_doc": "diary.pdf"})
    second = semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    before = [await snapshot(manager, first), await snapshot(manager, second)]

    stats = await run_cycle(manager, merge(first, second, TEA))

    assert stats.merged == 1
    [merged_id] = stats.undo.created
    demoted = await manager.get_memory(first.id)
    assert demoted is not None and demoted.importance == 0.05
    assert demoted.metadata["consolidated"] is True and demoted.metadata["source_doc"] == "diary.pdf"
    summary = await get_undo_summary(manager)
    assert summary is not None
    assert (summary.merged, summary.corrected, summary.updated) == (1, 0, 0)
    assert (summary.change_count, summary.conflict_count) == (3, 0)

    assert await undo(manager) == UndoResult(rolled_back=3)

    assert await manager.get_memory(merged_id) is None
    assert [await snapshot(manager, first), await snapshot(manager, second)] == before
    assert await get_undo_summary(manager) is None


async def test_undoing_a_rewrite_restores_the_text_the_importance_and_the_metadata_exactly(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    target = semantic("User uses vim", 1, importance=0.3, confidence=0.8, metadata={"note": "keep me"})
    other = semantic("Unrelated fact about gardening", 2)
    await seed(manager, [target, other])
    before = await snapshot(manager, target)

    stats = await run_cycle(manager, rewrite(target, "User uses neovim with lazy.nvim", 0.8))

    assert stats.updated == 1
    rewritten = await manager.get_memory(target.id)
    assert rewritten is not None and rewritten.content == "User uses neovim with lazy.nvim"
    assert rewritten.importance == 0.8 and "previous_content" in rewritten.metadata

    assert await undo(manager) == UndoResult(rolled_back=1)

    assert await snapshot(manager, target) == before


async def test_undoing_a_second_rewrite_brings_back_the_first_text_and_drops_the_marker_that_no_longer_applies(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    target = semantic("User uses vim", 1, importance=0.3)
    other = semantic("Unrelated fact about gardening", 2)
    await seed(manager, [target, other])
    await run_cycle(manager, rewrite(target, "User uses neovim", 0.5))
    # A lone new memory is analyzed together with the stored ones most similar to it.
    await store_fresh(manager, "User maintains a dotfiles repository")
    await run_cycle(manager, rewrite(target, "User uses neovim with lazy.nvim", 0.6))

    assert await undo(manager) == UndoResult(rolled_back=1)

    restored = await manager.get_memory(target.id)
    assert restored is not None and (restored.content, restored.importance) == ("User uses neovim", 0.5)
    # The marker named the text before the undone rewrite; the undone rewrite's text is not that text any more.
    assert "previous_content" not in restored.metadata


async def test_the_journal_keeps_the_state_before_the_first_write_when_a_memory_is_written_twice(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    fact = semantic("User uses vim", 1, importance=0.4)
    await seed(manager, [fact])
    journal = UndoJournal()
    writes = CycleWrites(manager, journal)

    await writes.update_memory(fact.id, importance=0.2)
    await writes.update_memory(fact.id, importance=0.1)

    assert journal.touched[fact.id].importance == 0.4


async def test_undoing_a_correction_deletes_the_correction_and_restores_the_original_exactly(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    original = semantic("The user lives in Berlin", 1, importance=0.4, confidence=0.8, metadata={"note": "keep me"})
    other = semantic("Unrelated fact about gardening", 2)
    await seed(manager, [original, other])
    before = await snapshot(manager, original)

    stats = await run_cycle(manager, correct(original, "The user lives in Munich"))

    assert stats.corrected == 1
    [correction_id] = stats.undo.created
    assert await snapshot(manager, original) != before

    assert await undo(manager) == UndoResult(rolled_back=2)

    assert await manager.get_memory(correction_id) is None
    assert await snapshot(manager, original) == before


async def test_undoing_a_confirmation_restores_the_confidence(new_manager: NewManager) -> None:
    manager = new_manager()
    fact = semantic("The user lives in Berlin", 1, importance=0.4, confidence=0.5)
    other = semantic("Unrelated fact about gardening", 2)
    await seed(manager, [fact, other])
    before = await snapshot(manager, fact)

    stats = await run_cycle(manager, correct(fact, "The user lives in Berlin"))

    assert (stats.updated, stats.undo.created) == (1, [])
    assert (await snapshot(manager, fact))[2] > 0.5

    assert await undo(manager) == UndoResult(rolled_back=1)

    assert await snapshot(manager, fact) == before


@pytest.mark.parametrize(
    ("state", "created"),
    [(MergeState.CONFLICT, 1), (MergeState.SUPPLEMENT, 0)],
    ids=["conflict keeps both versions", "supplement extends the text"],
)
async def test_undoing_the_other_correction_outcomes_restores_the_original_exactly(
    new_manager: NewManager, monkeypatch: pytest.MonkeyPatch, state: MergeState, created: int
) -> None:
    decision = MergeDecision(
        state=state,
        merged_content="The user lives in Berlin and works remotely",
        updated_confidence=0.35,
        candidate_confidence=0.35,
    )
    monkeypatch.setattr(DeterministicThreeStateMerger, "evaluate", lambda self, **_: decision)
    manager = new_manager()
    fact = semantic("The user lives in Berlin", 1, importance=0.4, confidence=0.8, metadata={"note": "keep me"})
    other = semantic("Unrelated fact about gardening", 2)
    await seed(manager, [fact, other])
    before = await snapshot(manager, fact)

    stats = await run_cycle(manager, correct(fact, "The user lives in Berlin and works remotely"))

    assert (stats.updated, len(stats.undo.created)) == (1, created)
    assert await snapshot(manager, fact) != before

    assert await undo(manager) == UndoResult(rolled_back=1 + created)

    assert await snapshot(manager, fact) == before


async def test_undoing_after_the_forgetting_step_archived_the_demoted_sources_brings_them_back(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    # Created 300 days ago: retention is high enough to keep them at importance 0.7, and too low once demoted.
    long_ago = -270 * 86_400
    first = semantic(TEA, long_ago, importance=0.7, metadata={"origin": "chat"})
    second = semantic(TEA_TOO, long_ago + 1, importance=0.7)
    await seed(manager, [first, second])
    before = [await snapshot(manager, first), await snapshot(manager, second)]
    await run_cycle(manager, merge(first, second, TEA))

    vector, _ = manager._vec()
    forgotten = await run_forgetting(vector, manager.config, namespaces=["global"])

    assert sorted(forgotten.archived_ids) == sorted([first.id, second.id])
    archived = await manager.get_memory(first.id)
    assert archived is not None and archived.status == MemoryStatus.ARCHIVED
    summary = await get_undo_summary(manager)
    assert summary is not None and summary.conflict_count == 0  # an archive does not count as the user's edit

    assert await undo(manager) == UndoResult(rolled_back=3)

    assert [await snapshot(manager, first), await snapshot(manager, second)] == before


async def test_a_memory_the_user_edited_after_the_cycle_is_left_as_the_user_made_it(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.7), semantic(TEA_TOO, 2, importance=0.7)
    target = semantic("User uses vim", 3, importance=0.3)
    await seed(manager, [first, second, target])
    await run_cycle(manager, merge(first, second, TEA), rewrite(target, "User uses neovim", 0.8))
    await manager.update_memory(target.id, content="User uses helix now")

    summary = await get_undo_summary(manager)
    assert summary is not None and (summary.change_count, summary.conflict_count) == (4, 1)

    assert await undo(manager) == UndoResult(rolled_back=3, skipped_conflict=1)

    kept = await manager.get_memory(target.id)
    assert kept is not None and kept.content == "User uses helix now"
    restored = await manager.get_memory(first.id)
    assert restored is not None and restored.importance == 0.7


async def test_a_merged_memory_the_user_edited_after_the_cycle_survives_the_undo(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    stats = await run_cycle(manager, merge(first, second, TEA))
    [merged_id] = stats.undo.created
    await manager.update_memory(merged_id, content="User drinks oolong tea every morning")

    assert await undo(manager) == UndoResult(rolled_back=2, skipped_conflict=1)

    kept = await manager.get_memory(merged_id)
    assert kept is not None and kept.content == "User drinks oolong tea every morning"


async def test_a_merged_memory_the_user_pinned_after_the_cycle_survives_the_undo(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    stats = await run_cycle(manager, merge(first, second, TEA))
    [merged_id] = stats.undo.created
    await manager.pin_memory(merged_id)

    assert await undo(manager) == UndoResult(rolled_back=2, skipped_conflict=1)

    assert await manager.get_memory(merged_id) is not None
    restored = await manager.get_memory(second.id)
    assert restored is not None and restored.importance == 0.9


async def test_a_protected_source_is_never_changed_and_so_never_restored(new_manager: NewManager) -> None:
    manager = new_manager()
    pinned, second = semantic(TEA, 1, importance=0.8, pinned=True), semantic(TEA_TOO, 2, importance=0.4)
    await seed(manager, [pinned, second])

    stats = await run_cycle(manager, merge(pinned, second, TEA))

    assert set(stats.undo.touched) == {second.id}
    assert await undo(manager) == UndoResult(rolled_back=2)
    kept = await manager.get_memory(pinned.id)
    assert kept is not None and kept.importance == 0.8
    restored = await manager.get_memory(second.id)
    assert restored is not None and restored.importance == 0.4


async def test_a_cycle_that_changed_nothing_leaves_the_earlier_undo_in_place(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    await run_cycle(manager, merge(first, second, TEA))
    earlier = await get_undo_summary(manager)

    await store_fresh(manager, "User owns a bicycle", "User rides to work")
    quiet = await run_cycle(manager)

    assert quiet.undo.change_count == 0
    assert await get_undo_summary(manager) == earlier
    assert await undo(manager) == UndoResult(rolled_back=3)


async def test_a_cycle_that_only_adds_insights_leaves_the_earlier_undo_in_place(new_manager: NewManager) -> None:
    manager = new_manager()
    _, _, merged_id = await merged_pair(manager)
    earlier = await get_undo_summary(manager)
    await store_fresh(manager, "User owns a bicycle", "User rides to work")

    await run_cycle(manager, insights=("User prefers low-effort commutes",))

    assert await get_undo_summary(manager) == earlier
    assert len(await stored_insights(manager)) == 1
    assert await undo(manager) == UndoResult(rolled_back=3)
    assert await manager.get_memory(merged_id) is None
    assert len(await stored_insights(manager)) == 1


async def test_an_insight_is_part_of_its_cycle_so_undoing_the_cycle_removes_it(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])

    stats = await run_cycle(manager, merge(first, second, TEA), insights=("User prefers low-effort commutes",))

    [merged_id, insight_id] = stats.undo.created
    assert await undo(manager) == UndoResult(rolled_back=4)
    assert await manager.get_memory(merged_id) is None
    assert await manager.get_memory(insight_id) is None


async def test_an_insight_of_a_rewrite_only_cycle_is_undone_with_it(new_manager: NewManager) -> None:
    manager = new_manager()
    target, other = semantic("User uses vim", 1, importance=0.3), semantic("Unrelated fact about gardening", 2)
    await seed(manager, [target, other])

    await run_cycle(manager, rewrite(target, "User uses neovim", 0.8), insights=("User prefers modal editors",))

    assert await undo(manager) == UndoResult(rolled_back=2)
    assert await stored_insights(manager) == []


async def test_the_card_of_an_older_cycle_cannot_undo_a_newer_one(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    await run_cycle(manager, merge(first, second, TEA))
    shown = await get_undo_summary(manager)
    assert shown is not None
    target, _ = await store_fresh(manager, "User writes commit messages", "User uses a standing desk")
    assert isinstance(target, SemanticMemory)
    await run_cycle(
        manager, UpdateContentOp(memory_id=target.id[:8], new_content="User writes commit messages in English")
    )

    assert await undo_last_consolidation(manager, shown.cycle_id) is None

    newer = await manager.get_memory(target.id)
    assert newer is not None and newer.content == "User writes commit messages in English"
    newest = await get_undo_summary(manager)
    assert newest is not None and newest.cycle_id != shown.cycle_id


async def test_a_cycle_can_be_undone_only_once(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    await run_cycle(manager, merge(first, second, TEA))
    summary = await get_undo_summary(manager)
    assert summary is not None

    assert await undo_last_consolidation(manager, summary.cycle_id) == UndoResult(rolled_back=3)

    assert await undo_last_consolidation(manager, summary.cycle_id) is None
    assert await get_undo_summary(manager) is None


async def test_an_unreadable_journal_is_ignored(new_manager: NewManager) -> None:
    manager = new_manager()
    await write_bookkeeping(manager, _UNDO_KEY, "{not json")

    assert await get_undo_summary(manager) is None
    assert await undo_last_consolidation(manager, "any") is None


async def test_clearing_every_memory_takes_the_undo_with_it(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    await run_cycle(manager, merge(first, second, TEA))
    assert await get_undo_summary(manager) is not None

    await manager.delete_all()

    assert await get_undo_summary(manager) is None
