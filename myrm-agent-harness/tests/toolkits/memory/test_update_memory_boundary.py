"""An update the memory cannot keep is refused with a reason its caller can act on.

A mock manager cannot show what a refused update leaves behind, nor that a score the model gets wrong
can make the memory unreadable. Each case drives a real manager over SQLite and an embedded Qdrant: the
tool answers, then the memory is read back.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.memory._internal.storage import MemoryError as StoreError
from myrm_agent_harness.toolkits.memory._internal.storage import MemoryRejectedError
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.manage_tool import build_memory_manage_tool
from myrm_agent_harness.toolkits.memory.agent_surface.transient_fact_boundary import (
    transient_fact_save_rejection_message,
)
from myrm_agent_harness.toolkits.memory.agent_surface.write_failure_feedback import write_failure_feedback
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

NewManager = Callable[..., MemoryManager]

ORIGINAL = "User prefers dark mode"
TRANSIENT = "Your order #123456 is out for delivery with courier"


async def store_original(manager: MemoryManager) -> SemanticMemory:
    stored = await manager.store(SemanticMemory(content=ORIGINAL, importance=0.5), _bypass_approval=True)
    assert isinstance(stored, SemanticMemory)
    return stored


async def read_back(manager: MemoryManager, memory_id: str) -> SemanticMemory:
    kept = await manager.get_memory(memory_id)
    assert isinstance(kept, SemanticMemory), "the memory is no longer readable"
    return kept


@pytest.mark.parametrize("importance", [8, 1.5, -0.1, float("nan")], ids=["ten-point-scale", "above", "below", "nan"])
async def test_an_importance_outside_the_scale_is_refused_and_the_memory_stays_as_it_was(
    new_manager: NewManager, importance: float
) -> None:
    manager = new_manager()
    tool = build_memory_manage_tool(manager, description="manage")
    stored = await store_original(manager)

    answer = await tool.ainvoke(
        {
            "action": "update",
            "memory_id": stored.id,
            "new_content": "User prefers light mode",
            "new_importance": importance,
        }
    )

    assert "between 0.0 and 1.0" in answer
    kept = await read_back(manager, stored.id)
    assert (kept.content, kept.importance) == (ORIGINAL, 0.5)


@pytest.mark.parametrize("importance", [0.0, 1.0])
async def test_the_ends_of_the_scale_are_accepted(new_manager: NewManager, importance: float) -> None:
    manager = new_manager()
    tool = build_memory_manage_tool(manager, description="manage")
    stored = await store_original(manager)

    answer = await tool.ainvoke(
        {
            "action": "update",
            "memory_id": stored.id,
            "new_content": "User prefers light mode",
            "new_importance": importance,
        }
    )

    assert answer == f"Memory updated (ID: {stored.id})"
    kept = await read_back(manager, stored.id)
    assert (kept.content, kept.importance) == ("User prefers light mode", importance)


async def test_a_confidence_outside_the_scale_is_refused_and_the_memory_stays_readable(new_manager: NewManager) -> None:
    manager = new_manager()
    stored = await store_original(manager)

    with pytest.raises(MemoryRejectedError, match=r"confidence must be between 0\.0 and 1\.0"):
        await manager.update_memory(stored.id, confidence=2.0)

    assert (await read_back(manager, stored.id)).confidence == stored.confidence


async def test_a_transient_rewrite_is_answered_with_the_guidance_and_leaves_the_memory_alone(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    tool = build_memory_manage_tool(manager, description="manage")
    stored = await store_original(manager)

    answer = await tool.ainvoke({"action": "update", "memory_id": stored.id, "new_content": TRANSIENT})

    assert answer == transient_fact_save_rejection_message()
    assert (await read_back(manager, stored.id)).content == ORIGINAL


async def test_storing_a_transient_fact_is_refused_with_the_guidance(new_manager: NewManager) -> None:
    manager = new_manager()

    with pytest.raises(MemoryRejectedError) as refused:
        await manager.store(SemanticMemory(content=TRANSIENT), _bypass_approval=True)

    assert str(refused.value) == transient_fact_save_rejection_message()


def test_a_rejected_write_passes_its_message_on_to_the_model() -> None:
    error = MemoryRejectedError("Not updated: importance must be between 0.0 and 1.0 (got 8).")

    assert write_failure_feedback("memory_manage", error, fallback="Failed to manage memory") == str(error)


def test_an_unexpected_store_failure_keeps_the_generic_answer_and_never_leaks_its_message() -> None:
    answer = write_failure_feedback("memory_manage", StoreError("qdrant at 10.0.0.7 timed out"), fallback="Failed")

    assert answer == "Failed"
