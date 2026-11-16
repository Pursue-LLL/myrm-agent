"""Architecture guard: a registry built for ``no_builtin_tools`` never holds a built-in meta tool.

Verifies that when no_builtin_tools is enabled:
1. ToolRegistry refuses ToolSource.META tools, so every view of it (resolve, snapshot, has_tool, tool_names) is one action space.
2. Pure domain custom tools completely control the action space, including one that shares a built-in's name.
3. An agent builds its registry from the runtime config.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.tools import tool

from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolSource
from myrm_agent_harness.agent.types import AgentRuntimeConfig


@tool
def custom_file_write(path: str, content: str) -> str:
    """Domain-specific custom file writer."""
    return f"written to {path}"


@tool
def built_in_meta_tool(query: str) -> str:
    """Built-in framework meta tool."""
    return "meta result"


@tool
def middleware_tool(query: str) -> str:
    """Tool a middleware contributes."""
    return "middleware result"


@tool("built_in_meta_tool")
def host_tool_named_like_a_built_in(query: str) -> str:
    """Host tool that reuses a built-in tool's name."""
    return "host result"


def _register_all(registry: ToolRegistry) -> None:
    registry.register_many([built_in_meta_tool], source=ToolSource.META)
    registry.register(custom_file_write, source=ToolSource.USER)
    registry.register(middleware_tool, source=ToolSource.MIDDLEWARE)


def test_a_registry_that_keeps_the_built_ins_holds_every_source() -> None:
    registry = ToolRegistry()

    _register_all(registry)

    assert registry.tool_names() == {"built_in_meta_tool", "custom_file_write", "middleware_tool"}
    assert {t.name for t in registry.resolve()} == registry.tool_names()


def test_a_registry_without_built_ins_holds_none_of_them_in_any_view() -> None:
    registry = ToolRegistry(no_builtin_tools=True)

    _register_all(registry)

    host_names = {"custom_file_write", "middleware_tool"}
    assert registry.tool_names() == host_names
    assert not registry.has_tool("built_in_meta_tool")
    assert {t.name for t in registry.resolve()} == host_names
    assert {s.name for s in registry.snapshot()} == host_names
    assert registry.entry_count == len(host_names)
    assert ToolSource.META not in registry.entries_by_source()


def test_host_tool_sharing_a_built_in_name_stays_when_built_ins_are_left_out() -> None:
    kept = ToolRegistry()
    kept.register(built_in_meta_tool, source=ToolSource.META)
    kept.register(host_tool_named_like_a_built_in, source=ToolSource.USER)
    left_out = ToolRegistry(no_builtin_tools=True)
    left_out.register(built_in_meta_tool, source=ToolSource.META)
    left_out.register(host_tool_named_like_a_built_in, source=ToolSource.USER)

    # Offered together, the built-in shadows the host tool by source priority.
    assert kept.resolve() == [built_in_meta_tool]
    # Leaving the built-ins out must not take the host tool's name with them.
    assert left_out.resolve() == [host_tool_named_like_a_built_in]


@pytest.mark.parametrize("no_builtin_tools", [False, True])
def test_snapshot_lists_the_tools_resolve_offers_with_and_without_built_ins(no_builtin_tools: bool) -> None:
    registry = ToolRegistry(no_builtin_tools=no_builtin_tools)
    registry.register(built_in_meta_tool, source=ToolSource.META)
    registry.register(host_tool_named_like_a_built_in, source=ToolSource.USER)
    registry.register(custom_file_write, source=ToolSource.USER)

    offered = [t.name for t in registry.resolve()]
    listed = [s.name for s in registry.snapshot()]

    assert listed == offered


@pytest.mark.parametrize("no_builtin_tools", [False, True])
def test_an_agent_builds_its_registry_from_the_runtime_config(no_builtin_tools: bool) -> None:
    agent = BaseAgent(llm=MagicMock(), tools=[], config=AgentRuntimeConfig(no_builtin_tools=no_builtin_tools))

    agent._tool_registry.register(built_in_meta_tool, source=ToolSource.META)

    assert agent._tool_registry.has_tool("built_in_meta_tool") is not no_builtin_tools
