"""A consolidation window is analyzed one namespace at a time, and only where the manager may write.

A namespace is the unit of who can read a memory and of the write fence: a model call that mixed namespaces could
fold a memory into a product readable by someone it was hidden from, or store a product outside the manager's grant.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryWritePolicy
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation import get_last_consolidated_at, run_consolidation
from myrm_agent_harness.toolkits.memory.strategies.consolidation_groups import analyze_group, writable_groups
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATED_FLAG_KEY,
    ConsolidationBatch,
    ConsolidationResponse,
    MergeOp,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import UndoResult
from myrm_agent_harness.toolkits.memory.types import MemoryScope, SemanticMemory
from tests.support.consolidation_cycles import CONFIG, TEA, TEA_TOO, merge, run_cycle, stored, undo
from tests.support.consolidation_manager import make_manager
from tests.support.consolidation_seeds import NewManager, llm_answering_in_turn, llm_returning, seed, semantic

COFFEE = "User takes coffee black without sugar"
COFFEE_TOO = "User prefers black coffee, no sugar"
PRIVATE = "User keeps a private journal"
STRATEGIES_LOGGER = "myrm_agent_harness.toolkits.memory.strategies"


def placed_in(memory: SemanticMemory, namespace: str) -> SemanticMemory:
    memory.scope = MemoryScope(primary_namespace=namespace, namespaces=[namespace])
    return memory


def note(namespace: str, text: str) -> SemanticMemory:
    return placed_in(SemanticMemory(content=text), namespace)


def manager_writing(*write: str, reading: Sequence[str] = ()) -> AsyncMock:
    manager = make_manager()
    manager.scope = MemoryScope(primary_namespace=write[0] if write else "", namespaces=list(write))
    manager.namespaces = list(reading)
    return manager


async def assert_untouched(manager: MemoryManager, *memories: SemanticMemory) -> None:
    """The store holds each memory as it was seeded: neither re-weighted nor folded into a merge."""
    for memory in memories:
        kept = await stored(manager, memory)
        assert kept.importance == memory.importance
        assert CONSOLIDATED_FLAG_KEY not in kept.metadata


def prompts_of(llm: MagicMock) -> list[str]:
    return [call.args[0][1].content for call in llm.with_structured_output.return_value.ainvoke.await_args_list]


def test_a_window_splits_by_primary_namespace_keeping_arrival_order() -> None:
    mine1, shared1, mine2, shared2 = (
        note("agent:x", "a1"),
        note("global", "g1"),
        note("agent:x", "a2"),
        note("global", "g2"),
    )

    groups = writable_groups(
        [mine1, shared1, mine2, shared2], manager_writing("agent:x", reading=["global", "agent:x"])
    )

    assert groups == [[mine1, mine2], [shared1, shared2]]


def test_a_namespace_with_a_single_memory_has_nothing_to_compare() -> None:
    lone, mine1, mine2 = note("global", "lone"), note("agent:x", "a1"), note("agent:x", "a2")

    assert writable_groups([lone, mine1, mine2], manager_writing("agent:x", reading=["global"])) == [[mine1, mine2]]


def test_neighbours_alone_have_nothing_new_to_compare() -> None:
    new, near, far1, far2 = note("global", "new"), note("global", "near"), note("agent:x", "f1"), note("agent:x", "f2")
    manager = manager_writing("agent:x", reading=["global"])

    assert writable_groups([new, near, far1, far2], manager, frozenset({new.id})) == [[new, near]]
    assert writable_groups([new, near, far1, far2], manager) == [[new, near], [far1, far2]]


def test_a_namespace_outside_the_write_scope_is_skipped_and_named(caplog: pytest.LogCaptureFixture) -> None:
    mine1, mine2, theirs1, theirs2 = (
        note("agent:x", "a1"),
        note("agent:x", "a2"),
        note("project:p", "p1"),
        note("project:p", "p2"),
    )
    manager = manager_writing("agent:x", reading=["global", "agent:x", "project:p"])

    with caplog.at_level(logging.INFO, logger=STRATEGIES_LOGGER):
        groups = writable_groups([theirs1, mine1, theirs2, mine2], manager)

    assert groups == [[mine1, mine2]]
    assert "project:p" in caplog.text


@pytest.mark.parametrize("shared", ["global", "shared:team"])
def test_a_broadcast_namespace_is_writable_only_for_a_manager_that_reads_it(shared: str) -> None:
    first, second = note(shared, "first"), note(shared, "second")

    assert writable_groups([first, second], manager_writing("agent:x", reading=[shared])) == [[first, second]]
    assert writable_groups([first, second], manager_writing("agent:x", reading=["agent:x"])) == []


def test_a_memory_spanning_a_namespace_outside_the_grant_blocks_its_group() -> None:
    wide = SemanticMemory(
        content="wide", scope=MemoryScope(primary_namespace="agent:x", namespaces=["agent:x", "project:p"])
    )

    assert writable_groups([wide, note("agent:x", "plain")], manager_writing("agent:x")) == []


def test_a_manager_without_a_write_scope_fences_nothing() -> None:
    memories = [note("agent:x", "a1"), note("agent:x", "a2"), note("project:p", "p1"), note("project:p", "p2")]

    assert len(writable_groups(memories, manager_writing())) == 2


async def test_the_model_is_shown_the_group_and_the_new_memory_is_marked() -> None:
    first, second = note("global", COFFEE), note("global", COFFEE_TOO)
    llm = llm_returning(ConsolidationResponse())

    batch = await analyze_group([first, second], llm, "2026-11-12", frozenset({first.id}))

    [prompt] = prompts_of(llm)
    assert COFFEE in prompt and COFFEE_TOO in prompt
    assert prompt.count("[NEW]") == 1
    assert batch == ConsolidationBatch(memories=[first, second])


async def test_an_answer_given_as_a_dict_is_validated_like_a_model() -> None:
    first, second = note("global", COFFEE), note("global", COFFEE_TOO)
    llm = llm_returning(ConsolidationResponse())
    llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value={"operations": [], "insights": [COFFEE]})

    assert (await analyze_group([first, second], llm, "2026-11-12", None)).insights == [COFFEE]


async def test_any_other_answer_type_is_an_error() -> None:
    llm = llm_returning(ConsolidationResponse())
    llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value="free text")

    with pytest.raises(TypeError, match="Unexpected response type"):
        await analyze_group([note("global", "a"), note("global", "b")], llm, "2026-11-12", None)


async def test_what_the_checks_turn_away_is_counted_on_the_batch() -> None:
    rent, utilities = note("global", "Rent is 4500 yuan"), note("global", "Utilities are 300 yuan")
    unknown_source = MergeOp(source_ids=[rent.id[:8], "ffffffff"], merged_content="Rent is 4500 yuan")
    llm = llm_returning(
        ConsolidationResponse(operations=[unknown_source], insights=["Rent and utilities come to 4800 yuan"])
    )

    batch = await analyze_group([rent, utilities], llm, "2026-11-12", None)

    assert (batch.operations, batch.insights, batch.rejected) == ([], [], 2)


async def seed_two_namespaces(
    manager: MemoryManager,
) -> tuple[tuple[SemanticMemory, SemanticMemory], tuple[SemanticMemory, SemanticMemory]]:
    """Two global and two ``agent:x`` memories, interleaved in arrival order."""
    in_global = semantic(TEA, 1), semantic(TEA_TOO, 3)
    in_agent = placed_in(semantic(COFFEE, 2), "agent:x"), placed_in(semantic(COFFEE_TOO, 4), "agent:x")
    await seed(manager, [in_global[0], in_agent[0], in_global[1], in_agent[1]])
    return in_global, in_agent


async def test_a_window_across_namespaces_is_analyzed_one_namespace_at_a_time(new_manager: NewManager) -> None:
    manager = new_manager(["global", "agent:x"])
    (g1, g2), (x1, x2) = await seed_two_namespaces(manager)
    llm = llm_answering_in_turn(
        ConsolidationResponse(operations=[merge(g1, g2, TEA)]),
        ConsolidationResponse(operations=[merge(x1, x2, COFFEE)]),
    )

    stats = await run_consolidation(manager, llm, CONFIG)

    assert (stats.merged, stats.input_count, stats.errors, stats.rejected) == (2, 4, 0, 0)
    in_global, in_agent = prompts_of(llm)
    assert TEA_TOO in in_global and COFFEE not in in_global and COFFEE_TOO not in in_global
    assert COFFEE_TOO in in_agent and TEA not in in_agent and TEA_TOO not in in_agent
    products = [await manager.get_memory(memory_id) for memory_id in stats.undo.created]
    assert sorted(product.scope.primary_namespace for product in products if product) == ["agent:x", "global"]


async def test_a_merge_cannot_reach_a_memory_of_another_namespace(new_manager: NewManager) -> None:
    manager = new_manager(["global", "agent:x"])
    (g1, g2), (x1, x2) = await seed_two_namespaces(manager)
    llm = llm_answering_in_turn(
        ConsolidationResponse(operations=[merge(g1, x1, TEA)]),  # x1 was never shown in the global group
        ConsolidationResponse(),
    )

    stats = await run_consolidation(manager, llm, CONFIG)

    assert (stats.merged, stats.rejected, stats.errors) == (0, 1, 0)
    await assert_untouched(manager, g1, g2, x1, x2)


async def test_the_groups_of_a_cycle_share_one_undo_slot(new_manager: NewManager) -> None:
    manager = new_manager(["global", "agent:x"])
    (g1, g2), (x1, x2) = await seed_two_namespaces(manager)
    llm = llm_answering_in_turn(
        ConsolidationResponse(operations=[merge(g1, g2, TEA)]),
        ConsolidationResponse(operations=[merge(x1, x2, COFFEE)]),
    )
    stats = await run_consolidation(manager, llm, CONFIG)

    assert await undo(manager) == UndoResult(rolled_back=6)  # two merges: two sources touched, one product created

    await assert_untouched(manager, g1, g2, x1, x2)
    assert [await manager.get_memory(memory_id) for memory_id in stats.undo.created] == [None, None]


async def test_a_group_the_model_fails_on_leaves_the_whole_window_unwritten_and_uncovered(
    new_manager: NewManager,
) -> None:
    manager = new_manager(["global", "agent:x"])
    (g1, g2), _ = await seed_two_namespaces(manager)
    llm = llm_returning(ConsolidationResponse())
    llm.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=[ConsolidationResponse(operations=[merge(g1, g2, TEA)]), RuntimeError("model down")]
    )

    stats = await run_consolidation(manager, llm, CONFIG)

    assert (stats.errors, stats.input_count, stats.merged) == (1, 4, 0)
    assert stats.undo.created == []
    assert await get_last_consolidated_at(manager) is None
    await assert_untouched(manager, g1, g2)


async def test_a_namespace_the_manager_may_not_write_is_not_consolidated(
    new_manager: NewManager, caplog: pytest.LogCaptureFixture
) -> None:
    policy = AgentMemoryPolicy(agent_id="x", write_policy=MemoryWritePolicy.AGENT)
    manager = new_manager(["global", "agent:x", "project:p"], agent_id="x", memory_policy=policy)
    project = placed_in(semantic(TEA, 1), "project:p"), placed_in(semantic(TEA_TOO, 3), "project:p")
    mine = placed_in(semantic(COFFEE, 2), "agent:x"), placed_in(semantic(COFFEE_TOO, 4), "agent:x")
    await seed(manager, [project[0], mine[0], project[1], mine[1]])
    llm = llm_returning(ConsolidationResponse(operations=[merge(*mine, COFFEE)]))

    with caplog.at_level(logging.INFO, logger=STRATEGIES_LOGGER):
        stats = await run_consolidation(manager, llm, CONFIG)

    assert llm.with_structured_output.return_value.ainvoke.await_count == 1
    assert (stats.merged, stats.input_count, stats.errors) == (1, 2, 0)
    assert "project:p" in caplog.text
    await assert_untouched(manager, *project)


async def test_a_lone_memory_is_enriched_only_with_memories_of_its_own_namespace(new_manager: NewManager) -> None:
    manager = new_manager(["global", "agent:x", "project:p"])
    private, earlier = placed_in(semantic(PRIVATE, 1), "agent:x"), placed_in(semantic(TEA, 2), "project:p")
    await seed(manager, [private, earlier])
    await run_cycle(manager)  # each is alone in its namespace, so nothing is asked of the model and both are covered
    await manager.store(placed_in(SemanticMemory(content=TEA_TOO), "project:p"), _bypass_approval=True)
    llm = llm_returning(ConsolidationResponse())

    await run_consolidation(manager, llm, CONFIG)

    [prompt] = prompts_of(llm)
    assert TEA in prompt and TEA_TOO in prompt and PRIVATE not in prompt


async def test_a_lone_memory_whose_neighbours_all_lie_elsewhere_asks_nothing_of_the_model(
    new_manager: NewManager,
) -> None:
    manager = new_manager(["global", "agent:x"])
    await seed(manager, [semantic(TEA, 1), semantic(TEA_TOO, 2)])
    await run_cycle(manager)  # the two global memories are compared with each other and covered
    covered = await get_last_consolidated_at(manager)
    await manager.store(placed_in(SemanticMemory(content=COFFEE), "agent:x"), _bypass_approval=True)
    llm = llm_returning(ConsolidationResponse())

    stats = await run_consolidation(manager, llm, CONFIG)

    assert prompts_of(llm) == []
    assert (stats.input_count, stats.errors) == (0, 0)
    advanced = await get_last_consolidated_at(manager)
    assert covered is not None and advanced is not None and advanced > covered


async def test_a_window_of_one_namespace_costs_one_model_call(new_manager: NewManager) -> None:
    manager = new_manager()
    await seed(manager, [semantic(TEA, 1), semantic(TEA_TOO, 2), semantic(COFFEE, 3)])
    llm = llm_returning(ConsolidationResponse())

    await run_consolidation(manager, llm, CONFIG)

    [prompt] = prompts_of(llm)
    assert TEA in prompt and TEA_TOO in prompt and COFFEE in prompt
