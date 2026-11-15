"""The MCP ``memory_store`` tool takes no keyword argument for a rule: a rule is found by its trigger and action text.

A ``rule_keywords`` argument was once offered as the rule's trigger keywords, yet nothing ever read what it stored.
A client built against that schema keeps sending it; the server ignores it like any argument it does not define, and
the rule is stored as sent.
"""

from __future__ import annotations

from collections.abc import Callable

from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemoryType, ProceduralMemory
from tests.support.memory_save_surfaces import save_with_mcp_tool

NewManager = Callable[..., MemoryManager]


async def test_the_store_tool_offers_no_keyword_argument(new_manager: NewManager) -> None:
    tools = await MemoryMCPServer(new_manager(), server_name="test-memory").mcp.list_tools()
    store = next(tool for tool in tools if tool.name == "memory_store")

    assert "rule_keywords" not in store.input_schema["properties"]
    assert "rule_keywords" not in (store.description or "")


async def test_a_client_that_still_sends_rule_keywords_gets_its_rule_stored_without_them(
    new_manager: NewManager,
) -> None:
    manager = new_manager()

    reply = await save_with_mcp_tool(
        manager,
        {
            "content": "Run the whole test suite",
            "category": "rule",
            "rule_trigger": "before merge",
            "rule_keywords": "deploy,release",
        },
    )

    assert reply.startswith("Rule stored"), reply
    (rule,) = await manager.list_memories(MemoryType.PROCEDURAL, limit=10)
    assert isinstance(rule, ProceduralMemory)
    assert (rule.trigger, rule.action) == ("before merge", "Run the whole test suite")
    assert not hasattr(rule, "trigger_keywords")
