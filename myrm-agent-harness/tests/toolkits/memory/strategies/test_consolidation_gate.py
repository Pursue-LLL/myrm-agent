"""What the apply step does when the memories an operation names changed while the model was thinking.

The model plans against the memories as it read them. The user may archive, edit, pin or delete one meanwhile, or a
concurrent cycle may fold it into a merge. Each case drives a real manager over SQLite and an embedded Qdrant,
because the promise is about what the stores hold afterwards: the operation is skipped whole (nothing written,
nothing to undo), the user's change stands, and the skip is a counted refusal, never an error that would hold the
window back.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import pytest

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation import get_last_consolidated_at, run_consolidation
from myrm_agent_harness.toolkits.memory.strategies.consolidation_gate import GateRefusal, admit
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATED_FLAG_KEY,
    ConsolidationResponse,
    is_folded_fragment,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import get_undo_summary
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, SemanticMemory
from tests.support.consolidation_cycles import (
    CONFIG,
    TEA,
    TEA_TOO,
    correct,
    merge,
    merged_pair,
    rewrite,
    store_fresh,
    stored,
)
from tests.support.consolidation_seeds import NewManager, llm_answering_after, seed, semantic

STRATEGIES_LOGGER = "myrm_agent_harness.toolkits.memory.strategies"
EDITED_TEXT = "User drinks oolong tea every morning"

UserAction = Callable[[MemoryManager, SemanticMemory], Awaitable[object]]


async def edit(manager: MemoryManager, memory: SemanticMemory) -> object:
    return await manager.update_memory(memory.id, content=EDITED_TEXT)


async def switch_off(manager: MemoryManager, memory: SemanticMemory) -> object:
    return await manager.update_memory(memory.id, status=MemoryStatus.DISABLED)


async def archive(manager: MemoryManager, memory: SemanticMemory) -> object:
    return await manager.update_memory(memory.id, status=MemoryStatus.ARCHIVED)


async def delete(manager: MemoryManager, memory: SemanticMemory) -> object:
    return await manager.delete_memory(manager.config.semantic_collection, [memory.id])


async def pin(manager: MemoryManager, memory: SemanticMemory) -> object:
    return await manager.pin_memory(memory.id)


async def lock_as_exact_fact(manager: MemoryManager, memory: SemanticMemory) -> object:
    return await manager.update_memory(memory.id, is_exact_fact=True)


async def fold(manager: MemoryManager, memory: SemanticMemory) -> object:
    return await manager.update_memory(memory.id, metadata={CONSOLIDATED_FLAG_KEY: True})


CHANGES: list[tuple[str, UserAction]] = [
    ("edited", edit),
    ("inactive", switch_off),
    ("inactive", archive),
    ("missing", delete),
    ("protected", pin),
    ("protected", lock_as_exact_fact),
    ("folded", fold),
]


@pytest.mark.parametrize(("reason", "act"), CHANGES, ids=[act.__name__ for _, act in CHANGES])
async def test_a_merge_is_refused_whole_when_a_source_changed_meanwhile(
    new_manager: NewManager, caplog: pytest.LogCaptureFixture, reason: str, act: UserAction
) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    llm = llm_answering_after(
        ConsolidationResponse(operations=[merge(first, second, TEA)]), lambda: act(manager, first)
    )

    with caplog.at_level(logging.INFO, logger=STRATEGIES_LOGGER):
        stats = await run_consolidation(manager, llm, CONFIG)

    assert (stats.merged, stats.rejected, stats.errors) == (0, 1, 0)
    assert stats.undo.change_count == 0
    assert f"{first.id} ({reason})" in caplog.text
    assert TEA not in caplog.text and TEA_TOO not in caplog.text  # a refusal names ids and the reason, never content
    untouched = await stored(manager, second)
    assert untouched.importance == 0.9 and not is_folded_fragment(untouched)
    assert await get_last_consolidated_at(manager) is not None  # a refusal is a skip: the window counts as covered


async def test_a_rewrite_does_not_overwrite_an_edit_the_user_made_meanwhile(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1), semantic(TEA_TOO, 2)
    await seed(manager, [first, second])
    response = ConsolidationResponse(operations=[rewrite(first, "User drinks green tea at dawn", 0.9)])

    stats = await run_consolidation(manager, llm_answering_after(response, lambda: edit(manager, first)), CONFIG)

    assert (stats.updated, stats.rejected, stats.errors) == (0, 1, 0)
    kept = await manager.get_memory(first.id)
    assert kept is not None and kept.content == EDITED_TEXT


async def test_a_correction_does_not_bring_back_a_memory_the_user_archived_meanwhile(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    first, second = semantic(TEA, 1), semantic(TEA_TOO, 2)
    await seed(manager, [first, second])
    response = ConsolidationResponse(operations=[correct(first, "User drinks oolong tea every morning")])

    stats = await run_consolidation(manager, llm_answering_after(response, lambda: archive(manager, first)), CONFIG)

    assert (stats.corrected, stats.updated, stats.rejected) == (0, 0, 1)
    assert stats.undo.created == []
    kept = await manager.get_memory(first.id)
    assert kept is not None and kept.status == MemoryStatus.ARCHIVED


async def test_a_refused_operation_does_not_stop_the_next_one(new_manager: NewManager) -> None:
    manager = new_manager()
    first, second, desk = semantic(TEA, 1), semantic(TEA_TOO, 2), semantic("User keeps a standing desk", 3)
    await seed(manager, [first, second, desk])
    response = ConsolidationResponse(
        operations=[merge(first, second, TEA), rewrite(desk, "User keeps a standing desk at work", 0.7)]
    )

    stats = await run_consolidation(manager, llm_answering_after(response, lambda: edit(manager, first)), CONFIG)

    assert (stats.merged, stats.updated, stats.rejected, stats.errors) == (0, 1, 1, 0)


async def test_a_cycle_whose_operations_are_all_refused_leaves_the_earlier_undo_in_place(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    await merged_pair(manager)
    earlier = await get_undo_summary(manager)
    first, second = await store_fresh(manager, "User owns a bicycle", "User rides to work")
    assert isinstance(first, SemanticMemory)
    response = ConsolidationResponse(operations=[merge(first, second, "User rides a bicycle to work")])

    stats = await run_consolidation(manager, llm_answering_after(response, lambda: edit(manager, first)), CONFIG)

    assert (stats.merged, stats.rejected) == (0, 1)
    assert await get_undo_summary(manager) == earlier


def _memory(**changes: object) -> SemanticMemory:
    return SemanticMemory(content="User drinks green tea").model_copy(update=changes)


def test_a_memory_that_is_still_what_the_model_read_is_admitted() -> None:
    memory = _memory()

    assert admit(memory, "User drinks green tea") is memory


@pytest.mark.parametrize(
    ("memory", "refusal"),
    [
        (None, GateRefusal.MISSING),
        (_memory(status=MemoryStatus.DISABLED), GateRefusal.INACTIVE),
        (_memory(status=MemoryStatus.ARCHIVED), GateRefusal.INACTIVE),
        (_memory(pinned=True), GateRefusal.PROTECTED),
        (_memory(is_user_locked=True), GateRefusal.PROTECTED),
        (_memory(is_exact_fact=True), GateRefusal.PROTECTED),
        (_memory(metadata={CONSOLIDATED_FLAG_KEY: True}), GateRefusal.FOLDED),
    ],
)
def test_a_memory_that_changed_state_is_refused_with_the_reason(
    memory: SemanticMemory | None, refusal: GateRefusal
) -> None:
    assert admit(memory, "User drinks green tea") is refusal


def test_a_memory_whose_text_changed_is_refused_as_edited() -> None:
    assert admit(_memory(), "User drinks black tea") is GateRefusal.EDITED


def test_the_state_is_judged_before_the_text() -> None:
    assert admit(_memory(status=MemoryStatus.ARCHIVED), "User drinks black tea") is GateRefusal.INACTIVE
