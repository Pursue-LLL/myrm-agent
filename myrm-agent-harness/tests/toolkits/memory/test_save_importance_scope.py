"""Only a knowledge save reads ``importance``.

The save description scopes the argument to knowledge, so the claim it makes must hold on both surfaces: a knowledge
save stores the value it is given, and every other category stores the same record whatever value is sent. The
argument itself carries the same note on both surfaces, because an MCP client lists the arguments with no other text.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from myrm_agent_harness.toolkits.memory.agent_surface._memory_agent_tool_descriptions import (
    MEMORY_SAVE_IMPORTANCE_FIELD_DESCRIPTION,
)
from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from tests.support.memory_save_surfaces import SAVES, Save, SaveArguments

NewManager = Callable[..., MemoryManager]

_STORED_ID = re.compile(r"\(ID: ([^)]+)\)")
_LOW, _HIGH = 0.1, 0.9

_OTHER_CATEGORIES = [
    pytest.param({"category": "event"}, id="event"),
    pytest.param({"category": "rule", "rule_trigger": "editing the schema"}, id="rule"),
    pytest.param({"category": "instruction"}, id="instruction"),
]


async def _stored_importance(
    manager: MemoryManager, save: Save, arguments: SaveArguments, content: str, importance: float
) -> float | None:
    """The importance of the memory a save stored; ``None`` for a memory type that has no such field."""
    reply = await save(manager, {**arguments, "content": content, "importance": importance})
    stored = _STORED_ID.search(reply)
    assert stored, reply
    memory = await manager.get_memory(stored.group(1))
    assert memory is not None
    return getattr(memory, "importance", None)


@pytest.mark.parametrize("save", SAVES)
async def test_a_knowledge_save_stores_the_importance_it_is_given(new_manager: NewManager, save: Save) -> None:
    manager = new_manager()
    knowledge = {"category": "knowledge"}

    low = await _stored_importance(manager, save, knowledge, "The design notes live in notebook A", _LOW)
    high = await _stored_importance(manager, save, knowledge, "The release notes live in notebook B", _HIGH)

    assert (low, high) == (_LOW, _HIGH)


@pytest.mark.parametrize("save", SAVES)
@pytest.mark.parametrize("arguments", _OTHER_CATEGORIES)
async def test_every_other_category_stores_the_same_whatever_importance_is_sent(
    new_manager: NewManager, save: Save, arguments: dict[str, str]
) -> None:
    manager = new_manager()

    low = await _stored_importance(manager, save, arguments, "Status updates stay under three lines", _LOW)
    high = await _stored_importance(manager, save, arguments, "Plans are written in the shared tracker", _HIGH)

    assert low == high


async def test_both_surfaces_scope_importance_at_the_argument_itself(new_manager: NewManager) -> None:
    manager = new_manager()
    agent_tool = next(tool for tool in create_memory_tools(manager) if tool.name == "memory_save_tool")
    mcp_tools = await MemoryMCPServer(manager, server_name="test-memory").mcp.list_tools()
    mcp_tool = next(tool for tool in mcp_tools if tool.name == "memory_store")

    on_agent = convert_to_openai_tool(agent_tool)["function"]["parameters"]["properties"]["importance"]["description"]
    on_mcp = mcp_tool.input_schema["properties"]["importance"]["description"]

    assert on_agent == on_mcp == MEMORY_SAVE_IMPORTANCE_FIELD_DESCRIPTION
    assert "knowledge" in on_mcp
