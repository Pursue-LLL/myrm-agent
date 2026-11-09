"""A consolidation cycle changes each memory once.

The model plans every operation against the memories as they were read, so an operation on a memory that an
earlier one already merged, corrected or rewrote has to be dropped before anything is written.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    ConsolidationOp,
    CorrectOp,
    MergeOp,
    UpdateContentOp,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_ops_executor import filter_and_guard_operations
from myrm_agent_harness.toolkits.memory.strategies.consolidation_prompts import _build_id_map
from myrm_agent_harness.toolkits.memory.types import SemanticMemory


def _window(*contents: str) -> tuple[list[SemanticMemory], dict[str, str]]:
    memories = [SemanticMemory(content=content) for content in contents]
    return memories, _build_id_map(memories)


def _short(id_map: dict[str, str], memory: SemanticMemory) -> str:
    return next(short for short, full in id_map.items() if full == memory.id)


def test_a_memory_merged_into_two_memories_is_merged_once() -> None:
    memories, id_map = _window("tea is good", "tea is great", "tea is the best")
    a, b, c = (_short(id_map, m) for m in memories)
    first = MergeOp(source_ids=[a, b], merged_content="tea is good and great")
    second = MergeOp(source_ids=[b, c], merged_content="tea is great and the best")

    kept, _ = filter_and_guard_operations([first, second], memories, id_map)

    assert kept == [first]


def test_a_memory_rewritten_after_it_was_merged_is_left_as_merged() -> None:
    memories, id_map = _window("tea is good", "tea is great")
    a, b = (_short(id_map, m) for m in memories)
    merge = MergeOp(source_ids=[a, b], merged_content="tea is good and great")
    rewrite = UpdateContentOp(memory_id=a, new_content="tea is fine")

    kept, _ = filter_and_guard_operations([merge, rewrite], memories, id_map)

    assert kept == [merge]


def test_the_same_memory_is_named_by_its_short_or_its_full_id() -> None:
    memories, id_map = _window("tea is good", "tea is great")
    first, second = memories
    rewrite = UpdateContentOp(memory_id=_short(id_map, first), new_content="tea is fine")
    correction = CorrectOp(memory_id=first.id, corrected_content="tea is fine indeed")

    kept, _ = filter_and_guard_operations([rewrite, correction], memories, id_map)

    assert kept == [rewrite]
    assert second.id in id_map.values()


def test_operations_on_different_memories_are_all_kept_in_the_order_proposed() -> None:
    memories, id_map = _window("tea is good", "tea is great", "coffee is bitter", "milk is white")
    a, b, c, d = (_short(id_map, m) for m in memories)
    ops: list[ConsolidationOp] = [
        MergeOp(source_ids=[a, b], merged_content="tea is good and great"),
        UpdateContentOp(memory_id=c, new_content="coffee is bitter and hot"),
        CorrectOp(memory_id=d, corrected_content="milk is white and cold"),
    ]

    kept, _ = filter_and_guard_operations(ops, memories, id_map)

    assert kept == ops


def test_an_operation_the_rubric_rejects_does_not_reserve_its_memories() -> None:
    memories, id_map = _window("tea is good", "tea is great")
    a = _short(id_map, memories[0])
    rejected = UpdateContentOp(memory_id=a, new_content="tea is awful", accuracy_score=0.1)
    accepted = UpdateContentOp(memory_id=a, new_content="tea is fine")

    kept, _ = filter_and_guard_operations([rejected, accepted], memories, id_map)

    assert kept == [accepted]


def test_a_dropped_operation_is_not_counted_as_guard_patched() -> None:
    memories, id_map = _window("Postgres runs on port 5433 at 127.0.0.1", "Database user is postgres")
    a, b = (_short(id_map, m) for m in memories)
    rewrite = UpdateContentOp(memory_id=a, new_content="Postgres runs on port 5433 at 127.0.0.1 locally")
    # The merged text drops the port, which the guard would patch back in if the merge were not dropped first.
    merge = MergeOp(source_ids=[a, b], merged_content="Postgres runs at 127.0.0.1 with user postgres")

    kept, patched = filter_and_guard_operations([rewrite, merge], memories, id_map)

    assert (kept, patched) == ([rewrite], 0)


def test_an_unknown_id_does_not_make_two_operations_overlap() -> None:
    memories, id_map = _window("tea is good", "tea is great", "coffee is bitter", "coffee is hot")
    a, b, c, d = (_short(id_map, m) for m in memories)
    first = MergeOp(source_ids=[a, b, "no-such-id"], merged_content="tea is good and great")
    second = MergeOp(source_ids=[c, d, "no-such-id"], merged_content="coffee is bitter and hot")

    kept, _ = filter_and_guard_operations([first, second], memories, id_map)

    assert kept == [first, second]
