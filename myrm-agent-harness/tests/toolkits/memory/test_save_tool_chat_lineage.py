"""A memory the agent saves during a chat is linked to that chat, so deleting the chat removes it.

The agent's own saves go through ``memory_save_tool``: into the chat session's buffer while that is allowed, and
straight through the manager when the user confirms saves first or the agent writes to the shared scope. Each path is
driven over a real manager and the link is read back from what the path left behind: the approval queue, the stored
memory and what the chat's deletion purges.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.memory.types import MemoryType, ProceduralMemory
from tests.support.consolidation_seeds import NewManager
from tests.support.memory_save_surfaces import SaveArguments, save_with_agent_tool, save_with_mcp_tool

KNOWLEDGE = {"category": "knowledge", "content": "The user keeps design notes in a shared notebook"}
EVENT = {"category": "event", "content": "The user finished the data export for the audit"}
RULE = {"category": "rule", "content": "Ask before changing the schema", "rule_trigger": "editing the schema"}
INSTRUCTION = {"category": "instruction", "content": "Keep status updates under three lines"}
# Only knowledge and events are vector writes, so only they have a write target.
VECTOR_CATEGORIES = [
    pytest.param(KNOWLEDGE, {"semantic": 1}, id="knowledge"),
    pytest.param(EVENT, {"episodic": 1}, id="event"),
]
ALL_CATEGORIES = [
    *VECTOR_CATEGORIES,
    pytest.param(RULE, {"procedural": 1}, id="rule"),
    pytest.param(INSTRUCTION, {"procedural": 1}, id="instruction"),
]


@pytest.mark.parametrize(("arguments", "stored_as"), ALL_CATEGORIES)
async def test_a_save_that_waits_for_approval_names_its_chat_before_and_after_approval(
    new_manager: NewManager, arguments: SaveArguments, stored_as: dict[str, int]
) -> None:
    manager = new_manager(approval_required=True)
    manager.begin_session("chat-a")

    await save_with_agent_tool(manager, arguments)

    [queued] = await manager.list_pending()
    assert queued.source_chat_id == "chat-a"
    approved = await manager.approve(queued.id)
    assert approved is not None
    assert await manager.count_by_source_chat_id("chat-a") == {**stored_as, "pending": 1}
    await manager.purge_by_source_chat_id("chat-a")
    assert await manager.count_by_source_chat_id("chat-a") == {}


@pytest.mark.parametrize(("arguments", "stored_as"), VECTOR_CATEGORIES)
async def test_a_save_to_the_shared_scope_names_its_chat(
    new_manager: NewManager, arguments: SaveArguments, stored_as: dict[str, int]
) -> None:
    manager = new_manager()
    manager.begin_session("chat-a")

    await save_with_agent_tool(manager, {**arguments, "write_target": "shared"})

    assert await manager.count_by_source_chat_id("chat-a") == stored_as


@pytest.mark.parametrize(("arguments", "stored_as"), ALL_CATEGORIES)
async def test_a_buffered_save_names_its_chat_when_the_session_ends(
    new_manager: NewManager, arguments: SaveArguments, stored_as: dict[str, int]
) -> None:
    manager = new_manager()
    manager.begin_session("chat-a")

    await save_with_agent_tool(manager, arguments)
    await manager.end_session()

    assert await manager.count_by_source_chat_id("chat-a") == stored_as


async def test_a_rule_saved_outside_any_chat_names_none(new_manager: NewManager) -> None:
    manager = new_manager()

    await save_with_agent_tool(manager, RULE)

    [rule] = await manager.list_memories(MemoryType.PROCEDURAL)
    assert isinstance(rule, ProceduralMemory)
    assert rule.source_chat_id is None


async def test_a_save_over_the_mcp_server_belongs_to_no_chat(new_manager: NewManager) -> None:
    manager = new_manager()
    manager.begin_session("chat-a")

    await save_with_mcp_tool(manager, KNOWLEDGE)

    assert await manager.count_by_source_chat_id("chat-a") == {}
    assert await manager.count_memories(MemoryType.SEMANTIC) == 1


# A preference is a profile fact the user keeps: only its proposal belongs to the chat, and the key that holds a chat's
# own digest is the one entry a save can bind to its chat.
PREFERENCE = {"category": "preference", "content": "brief answers", "preference_key": "reply_style"}
DIGEST = {"category": "preference", "content": "Quarterly report done", "preference_key": "__working_state"}


async def test_a_preference_that_waits_for_approval_names_its_chat_and_the_approved_fact_stays(
    new_manager: NewManager,
) -> None:
    manager = new_manager(approval_required=True)
    manager.begin_session("chat-a")

    await save_with_agent_tool(manager, PREFERENCE)

    [queued] = await manager.list_pending()
    assert queued.source_chat_id == "chat-a"
    await manager.approve(queued.id)
    assert await manager.count_by_source_chat_id("chat-a") == {"pending": 1}
    await manager.purge_by_source_chat_id("chat-a")
    assert await manager.get_profile_attribute("reply_style") == "brief answers"
    assert await manager.count_by_source_chat_id("chat-a") == {}


async def test_a_preference_proposal_is_discarded_with_its_chat(new_manager: NewManager) -> None:
    manager = new_manager(approval_required=True)
    manager.begin_session("chat-a")
    await save_with_agent_tool(manager, PREFERENCE)

    assert await manager.count_by_source_chat_id("chat-a") == {"pending": 1}
    await manager.purge_by_source_chat_id("chat-a")

    assert await manager.list_pending() == []
    assert await manager.get_profile_attribute("reply_style") is None


async def test_a_saved_digest_is_bound_to_its_chat_and_an_ordinary_preference_is_not(new_manager: NewManager) -> None:
    manager = new_manager()
    manager.begin_session("chat-a")

    await save_with_agent_tool(manager, PREFERENCE)
    await save_with_agent_tool(manager, DIGEST)

    assert await manager.count_by_source_chat_id("chat-a") == {"profile": 1}
    await manager.purge_by_source_chat_id("chat-a")
    assert await manager.get_profile_attribute("__working_state") is None
    assert await manager.get_profile_attribute("reply_style") == "brief answers"


async def test_a_preference_saved_over_the_mcp_server_belongs_to_no_chat(new_manager: NewManager) -> None:
    manager = new_manager(approval_required=True)
    manager.begin_session("chat-a")

    await save_with_mcp_tool(manager, PREFERENCE)

    [queued] = await manager.list_pending()
    assert queued.source_chat_id is None
    assert await manager.count_by_source_chat_id("chat-a") == {}
