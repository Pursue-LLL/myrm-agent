"""The agent's own memory saves follow the manager's approval switch and report what really happened.

A user who turns "confirm before saving" on expects nothing the agent decides to remember to take
effect until they approve it, whichever category the agent picks and whichever surface (the in-process
``memory_save_tool`` or the MCP ``memory_store`` tool) it writes through.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import AnyMemory, MemoryType

NewManager = Callable[..., MemoryManager]
Save = Callable[[MemoryManager, dict[str, str]], Awaitable[str]]

KNOWLEDGE = {"category": "knowledge", "content": "The user keeps design notes in a shared notebook"}
CASES = [
    pytest.param(KNOWLEDGE, "Knowledge", MemoryType.SEMANTIC, id="knowledge"),
    pytest.param(
        {"category": "event", "content": "The user finished the data export for the audit"},
        "Event",
        MemoryType.EPISODIC,
        id="event",
    ),
    pytest.param(
        {"category": "rule", "content": "Ask before changing the schema", "rule_trigger": "editing the schema"},
        "Rule",
        MemoryType.PROCEDURAL,
        id="rule",
    ),
    pytest.param(
        {"category": "instruction", "content": "Keep status updates under three lines"},
        "Instruction",
        MemoryType.PROCEDURAL,
        id="instruction",
    ),
]


async def save_with_agent_tool(manager: MemoryManager, arguments: dict[str, str]) -> str:
    tool = next(tool for tool in create_memory_tools(manager) if tool.name == "memory_save_tool")
    return await tool.ainvoke(arguments)


async def save_with_mcp_tool(manager: MemoryManager, arguments: dict[str, str]) -> str:
    result = await MemoryMCPServer(manager, server_name="test-memory").mcp.call_tool("memory_store", dict(arguments))
    return "".join(str(getattr(block, "text", "")) for block in result.content)


SAVES = [pytest.param(save_with_agent_tool, id="agent-tool"), pytest.param(save_with_mcp_tool, id="mcp-tool")]


@pytest.mark.parametrize("save", SAVES)
@pytest.mark.parametrize(("arguments", "label", "memory_type"), CASES)
async def test_a_gated_save_waits_for_approval_and_says_so(
    new_manager: NewManager, save: Save, arguments: dict[str, str], label: str, memory_type: MemoryType
) -> None:
    manager = new_manager(approval_required=True)

    result = await save(manager, arguments)

    # No ID is reported: nothing was stored under one yet.
    assert result == f"{label} submitted for approval"
    assert await manager.count_memories(memory_type) == 0
    [queued] = await manager.list_pending()
    # A rule is queued in its "When … → Do …" form, so the agent's wording is contained, not equal.
    assert arguments["content"] in queued.content

    approved = await manager.approve(queued.id)

    assert approved is not None
    assert await manager.count_memories(memory_type) == 1
    assert await manager.list_pending() == []


@pytest.mark.parametrize("save", SAVES)
@pytest.mark.parametrize(("arguments", "label", "memory_type"), CASES)
async def test_an_ungated_save_is_stored_at_once(
    new_manager: NewManager, save: Save, arguments: dict[str, str], label: str, memory_type: MemoryType
) -> None:
    manager = new_manager()

    result = await save(manager, arguments)

    assert result.startswith(f"{label} stored (ID: ")
    assert await manager.count_memories(memory_type) == 1
    assert await manager.list_pending() == []


async def test_a_gated_save_skips_the_session_buffer(new_manager: NewManager) -> None:
    manager = new_manager(approval_required=True)
    session = manager.begin_session(chat_id="chat-1")

    result = await save_with_agent_tool(manager, KNOWLEDGE)

    assert result == "Knowledge submitted for approval"
    assert session.buffer_size == 0
    assert len(await manager.list_pending()) == 1


@pytest.mark.parametrize("save", SAVES)
async def test_saving_what_already_awaits_approval_is_refused_with_a_reason(
    new_manager: NewManager, save: Save
) -> None:
    manager = new_manager(approval_required=True)
    assert await save(manager, KNOWLEDGE) == "Knowledge submitted for approval"

    again = await save(manager, KNOWLEDGE)

    assert "already waiting for the user's approval" in again
    assert "Do not save it again" in again
    assert len(await manager.list_pending()) == 1


@pytest.mark.parametrize("save", SAVES)
async def test_parallel_identical_saves_queue_a_single_proposal(new_manager: NewManager, save: Save) -> None:
    """An agent may emit the same save several times in one step; only the first may be queued."""
    manager = new_manager(approval_required=True)

    results = await asyncio.gather(*(save(manager, KNOWLEDGE) for _ in range(6)))

    submitted = "Knowledge submitted for approval"
    assert results.count(submitted) == 1
    assert all("already waiting for the user's approval" in result for result in results if result != submitted)
    assert len(await manager.list_pending()) == 1


async def test_internal_writers_are_not_held_back_by_the_switch(new_manager: NewManager) -> None:
    """Only the agent's own saves honour the switch; the user's edits and framework writes store at once."""
    manager = new_manager(approval_required=True)

    stored = await manager.add_knowledge("The user edited this note by hand")

    assert await manager.get_memory(stored.id) is not None
    assert await manager.list_pending() == []


Add = Callable[[MemoryManager, bool], Awaitable[AnyMemory]]

ADD_HELPERS = [
    pytest.param(
        lambda manager, honor: manager.add_knowledge(
            "The team keeps its wiki in a shared notebook", honor_approval=honor
        ),
        MemoryType.SEMANTIC,
        id="knowledge",
    ),
    pytest.param(
        lambda manager, honor: manager.add_event("The audit export finished", honor_approval=honor),
        MemoryType.EPISODIC,
        id="event",
    ),
    pytest.param(
        lambda manager, honor: manager.add_pitfall(
            "The export timed out", failure_reason="timeout", negative_lesson="split the export", honor_approval=honor
        ),
        MemoryType.EPISODIC,
        id="pitfall",
    ),
    pytest.param(
        lambda manager, honor: manager.add_rule("editing the schema", "ask first", honor_approval=honor),
        MemoryType.PROCEDURAL,
        id="rule",
    ),
]


@pytest.mark.parametrize(("add", "memory_type"), ADD_HELPERS)
async def test_every_add_helper_stores_at_once_by_default(
    new_manager: NewManager, add: Add, memory_type: MemoryType
) -> None:
    manager = new_manager(approval_required=True)

    stored = await add(manager, False)

    assert await manager.count_memories(memory_type) == 1
    assert "_pending_id" not in stored.metadata
    assert await manager.list_pending() == []


@pytest.mark.parametrize(("add", "memory_type"), ADD_HELPERS)
async def test_every_add_helper_queues_when_the_caller_defers_to_the_switch(
    new_manager: NewManager, add: Add, memory_type: MemoryType
) -> None:
    manager = new_manager(approval_required=True)

    candidate = await add(manager, True)

    assert await manager.count_memories(memory_type) == 0
    [queued] = await manager.list_pending()
    assert candidate.metadata["_pending_id"] == queued.id
