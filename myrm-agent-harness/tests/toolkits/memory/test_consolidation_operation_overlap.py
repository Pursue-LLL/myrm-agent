"""A consolidation cycle changes each memory once, and only the memories the model was shown.

The model plans every operation against the memories as they were read, so an operation on a memory that an
earlier one already merged, corrected or rewrote has to be dropped before anything is written; one that names a
memory outside the analyzed set, or a merge of fewer than two distinct memories, never reaches the store.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    ConsolidationOp,
    CorrectOp,
    MergeOp,
    UpdateContentOp,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_ops_filter import filter_and_guard_operations
from myrm_agent_harness.toolkits.memory.strategies.consolidation_prompts import _build_id_map
from myrm_agent_harness.toolkits.memory.types import SemanticMemory


def _window(*contents: str) -> tuple[list[SemanticMemory], dict[str, str]]:
    memories = [SemanticMemory(content=content) for content in contents]
    return memories, _build_id_map(memories)


def _short(id_map: dict[str, str], memory: SemanticMemory) -> str:
    return next(short for short, full in id_map.items() if full == memory.id)


def test_a_memory_merged_into_two_memories_is_merged_once() -> None:
    memories, id_map = _window("tea is good", "tea is great", "tea is the best")
    a, b, c = (m.id for m in memories)
    first = MergeOp(source_ids=[a, b], merged_content="tea is good and great")
    second = MergeOp(source_ids=[b, c], merged_content="tea is great and the best")

    result = filter_and_guard_operations([first, second], memories, id_map)

    assert result.operations == [first]
    assert result.rejected == 1


def test_a_memory_rewritten_after_it_was_merged_is_left_as_merged() -> None:
    memories, id_map = _window("tea is good", "tea is great")
    a, b = (m.id for m in memories)
    merge = MergeOp(source_ids=[a, b], merged_content="tea is good and great")
    rewrite = UpdateContentOp(memory_id=a, new_content="tea is fine")

    result = filter_and_guard_operations([merge, rewrite], memories, id_map)

    assert result.operations == [merge]


def test_the_same_memory_is_named_by_its_short_or_its_full_id() -> None:
    memories, id_map = _window("tea is good", "tea is great")
    first, second = memories
    rewrite = UpdateContentOp(memory_id=_short(id_map, first), new_content="tea is fine")
    correction = CorrectOp(memory_id=first.id, corrected_content="tea is fine indeed")

    result = filter_and_guard_operations([rewrite, correction], memories, id_map)

    assert result.operations == [rewrite.model_copy(update={"memory_id": first.id})]
    assert second.id in id_map.values()


def test_short_ids_leave_the_filter_as_full_ids() -> None:
    memories, id_map = _window("tea is good", "tea is great", "coffee is bitter", "milk is white")
    a, b, c, d = (_short(id_map, m) for m in memories)
    ops: list[ConsolidationOp] = [
        MergeOp(source_ids=[a, b], merged_content="tea is good and great"),
        UpdateContentOp(memory_id=c, new_content="coffee is bitter and hot"),
        CorrectOp(memory_id=d, corrected_content="milk is white and cold"),
    ]

    kept = filter_and_guard_operations(ops, memories, id_map).operations

    assert isinstance(kept[0], MergeOp) and kept[0].source_ids == [memories[0].id, memories[1].id]
    assert isinstance(kept[1], UpdateContentOp) and kept[1].memory_id == memories[2].id
    assert isinstance(kept[2], CorrectOp) and kept[2].memory_id == memories[3].id


def test_operations_on_different_memories_are_all_kept_in_the_order_proposed() -> None:
    memories, id_map = _window("tea is good", "tea is great", "coffee is bitter", "milk is white")
    a, b, c, d = (m.id for m in memories)
    ops: list[ConsolidationOp] = [
        MergeOp(source_ids=[a, b], merged_content="tea is good and great"),
        UpdateContentOp(memory_id=c, new_content="coffee is bitter and hot"),
        CorrectOp(memory_id=d, corrected_content="milk is white and cold"),
    ]

    result = filter_and_guard_operations(ops, memories, id_map)

    assert (result.operations, result.rejected) == (ops, 0)


def test_an_operation_the_rubric_rejects_does_not_reserve_its_memories() -> None:
    memories, id_map = _window("tea is good", "tea is great")
    a = memories[0].id
    rejected = UpdateContentOp(memory_id=a, new_content="tea is awful", accuracy_score=0.1)
    accepted = UpdateContentOp(memory_id=a, new_content="tea is fine")

    result = filter_and_guard_operations([rejected, accepted], memories, id_map)

    assert (result.operations, result.rejected) == ([accepted], 1)


def test_a_dropped_operation_is_not_counted_as_guard_patched() -> None:
    memories, id_map = _window("Postgres runs on port 5433 at 127.0.0.1", "Database user is postgres")
    a, b = (m.id for m in memories)
    rewrite = UpdateContentOp(memory_id=a, new_content="Postgres runs on port 5433 at 127.0.0.1 locally")
    # The merged text drops the port, which the guard would patch back in if the merge were not dropped first.
    merge = MergeOp(source_ids=[a, b], merged_content="Postgres runs at 127.0.0.1 with user postgres")

    result = filter_and_guard_operations([rewrite, merge], memories, id_map)

    assert (result.operations, result.guard_patched, result.rejected) == ([rewrite], 0, 1)


def test_an_operation_naming_a_memory_the_model_was_not_shown_is_rejected_and_reserves_nothing() -> None:
    memories, id_map = _window("tea is good", "tea is great", "coffee is bitter")
    a, b, _ = (m.id for m in memories)
    stray = MergeOp(source_ids=[a, "no-such-id"], merged_content="tea is good and great")
    honest = MergeOp(source_ids=[a, b], merged_content="tea is good and great")

    result = filter_and_guard_operations([stray, honest], memories, id_map)

    assert (result.operations, result.rejected) == ([honest], 1)


def test_a_merge_of_one_memory_named_twice_is_rejected() -> None:
    memories, id_map = _window("tea is good", "tea is great")
    a = memories[0].id
    twice = MergeOp(source_ids=[a, _short(id_map, memories[0])], merged_content="tea is good")

    result = filter_and_guard_operations([twice], memories, id_map)

    assert (result.operations, result.rejected) == ([], 1)
