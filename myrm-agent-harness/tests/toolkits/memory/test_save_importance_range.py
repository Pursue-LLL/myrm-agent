"""A knowledge save refuses an importance outside the 0-1 scale, says why, and holds nothing back.

An update already answers a bad score with the reason (``test_update_memory_boundary``). A save of the same score
used to fall through to the generic failure, which gave the model nothing to retry with. The score is checked before
the session buffer, the approval queue and the store, so a refused save leaves nothing to flush or approve; a category
that ignores the score never fails on it.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.manage_tool import build_memory_manage_tool
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory
from tests.support.memory_save_surfaces import SAVES, Save, save_with_agent_tool

NewManager = Callable[..., MemoryManager]

FACT = "The design notes live in notebook A"
_STORED_ID = re.compile(r"\(ID: ([^)]+)\)")

_OUT_OF_RANGE = [
    pytest.param(8, id="ten-point-scale"),
    pytest.param(90, id="percent"),
    pytest.param(1.5, id="above"),
    pytest.param(-1, id="below"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="infinite"),
]

_CATEGORIES_THAT_IGNORE_IT = [
    pytest.param({"category": "event"}, id="event"),
    pytest.param({"category": "rule", "rule_trigger": "editing the schema"}, id="rule"),
    pytest.param({"category": "instruction"}, id="instruction"),
]


@pytest.mark.parametrize("save", SAVES)
@pytest.mark.parametrize("importance", _OUT_OF_RANGE)
async def test_a_score_outside_the_scale_is_refused_with_the_reason_and_nothing_is_stored(
    new_manager: NewManager, save: Save, importance: float
) -> None:
    manager = new_manager()

    reply = await save(manager, {"content": FACT, "importance": importance})

    assert reply.startswith("Not saved: importance must be between 0.0 and 1.0")
    assert "Retry with a value in that range" in reply
    assert await manager.count_memories(MemoryType.SEMANTIC) == 0


@pytest.mark.parametrize("save", SAVES)
@pytest.mark.parametrize("importance", [0.0, 1.0])
async def test_both_ends_of_the_scale_are_stored_as_given(
    new_manager: NewManager, save: Save, importance: float
) -> None:
    manager = new_manager()

    reply = await save(manager, {"content": FACT, "importance": importance})

    stored = _STORED_ID.search(reply)
    assert stored, reply
    memory = await manager.get_memory(stored.group(1))
    assert isinstance(memory, SemanticMemory)
    assert memory.importance == importance


async def test_a_refused_score_is_not_held_in_the_session_buffer(new_manager: NewManager) -> None:
    manager = new_manager()
    session = manager.begin_session(chat_id="chat-1")

    refused = await save_with_agent_tool(manager, {"content": FACT, "importance": 8})
    assert refused.startswith("Not saved:")
    assert session.buffer_size == 0

    buffered = await save_with_agent_tool(manager, {"content": FACT, "importance": 0.8})
    assert buffered.startswith("Knowledge buffered")
    assert session.buffer_size == 1


@pytest.mark.parametrize("save", SAVES)
async def test_a_refused_score_is_not_queued_for_approval(new_manager: NewManager, save: Save) -> None:
    manager = new_manager(approval_required=True)

    refused = await save(manager, {"content": FACT, "importance": 8})
    assert refused.startswith("Not saved:")
    assert await manager.list_pending() == []

    queued = await save(manager, {"content": FACT, "importance": 0.8})
    assert queued == "Knowledge submitted for approval"
    assert len(await manager.list_pending()) == 1


@pytest.mark.parametrize("save", SAVES)
@pytest.mark.parametrize("arguments", _CATEGORIES_THAT_IGNORE_IT)
async def test_a_category_that_ignores_the_score_never_fails_on_it(
    new_manager: NewManager, save: Save, arguments: dict[str, str]
) -> None:
    manager = new_manager()

    reply = await save(manager, {**arguments, "content": "Status updates stay under three lines", "importance": 8})

    assert _STORED_ID.search(reply), reply
    assert not reply.startswith("Not saved")


async def test_save_and_update_refuse_a_bad_score_in_the_same_words(new_manager: NewManager) -> None:
    manager = new_manager()
    stored = await manager.add_knowledge(FACT, importance=0.5)
    manage = build_memory_manage_tool(manager, description="manage")

    saved = await save_with_agent_tool(manager, {"content": "The release notes live in notebook B", "importance": 8})
    updated = await manage.ainvoke(
        {"action": "update", "memory_id": stored.id, "new_content": FACT, "new_importance": 8}
    )

    assert saved.removeprefix("Not saved: ") == updated.removeprefix("Not updated: ")
