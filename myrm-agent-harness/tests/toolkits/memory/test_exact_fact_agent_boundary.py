"""The agent edits a fact only the classifier flagged; a fact the user pinned stays out of its reach.

``is_exact_fact`` is a machine stamp that protects against lossy compression, so it must not lock the
agent out of correcting a stale address. A pin is the user's own decision and always holds.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.memory._internal.storage import MemoryProtectedError
from myrm_agent_harness.toolkits.memory.agent_surface.memory_manage_core import manage_memory
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

NewManager = Callable[..., MemoryManager]

STALE = "The staging server is reachable at 10.0.0.5:8080"
MOVED = "The staging server moved to 10.0.0.6:8080"


async def remember(manager: MemoryManager, content: str) -> SemanticMemory:
    stored = await manager.store(SemanticMemory(content=content), _bypass_approval=True)
    assert isinstance(stored, SemanticMemory)
    return stored


async def test_an_agent_can_update_a_fact_only_the_classifier_flagged(new_manager: NewManager) -> None:
    manager = new_manager()
    flagged = await remember(manager, STALE)
    assert flagged.is_user_protected and not flagged.pinned

    result = await manage_memory(manager, action="update", memory_id=flagged.id, new_content=MOVED)

    assert result.startswith("Memory updated")
    reloaded = await manager.get_memory(flagged.id)
    assert reloaded is not None
    assert reloaded.content == MOVED
    assert reloaded.is_exact_fact is True


async def test_an_agent_can_correct_a_fact_only_the_classifier_flagged(new_manager: NewManager) -> None:
    manager = new_manager()
    flagged = await remember(manager, STALE)

    result = await manage_memory(manager, action="correct", memory_id=flagged.id, new_content=MOVED)

    assert result.startswith("Memory corrected")


@pytest.mark.parametrize("action", ["update", "correct"])
async def test_an_agent_cannot_change_a_pinned_fact(new_manager: NewManager, action: str) -> None:
    manager = new_manager()
    pinned = await remember(manager, STALE)
    await manager.pin_memory(pinned.id)

    with pytest.raises(MemoryProtectedError):
        await manage_memory(manager, action=action, memory_id=pinned.id, new_content=MOVED)

    reloaded = await manager.get_memory(pinned.id)
    assert reloaded is not None
    assert reloaded.content == STALE
