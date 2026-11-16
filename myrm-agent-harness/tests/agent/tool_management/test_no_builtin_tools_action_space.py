"""Architecture guard: test pure domain no_builtin_tools action space overriding.

Verifies that when no_builtin_tools is enabled:
1. ToolRegistry excludes ToolSource.META tools from resolve() and snapshot(), before names are de-duplicated.
2. Pure domain custom tools completely control the action space, including one that shares a built-in's name.
"""

from __future__ import annotations

from langchain_core.tools import tool

from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolSource


@tool
def custom_file_write(path: str, content: str) -> str:
    """Domain-specific custom file writer."""
    return f"written to {path}"


@tool
def built_in_meta_tool(query: str) -> str:
    """Built-in framework meta tool."""
    return "meta result"


@tool("built_in_meta_tool")
def host_tool_named_like_a_built_in(query: str) -> str:
    """Host tool that reuses a built-in tool's name."""
    return "host result"


def test_tool_registry_no_builtin_tools_filtering() -> None:
    registry = ToolRegistry()
    registry.register(built_in_meta_tool, source=ToolSource.META)
    registry.register(custom_file_write, source=ToolSource.USER)

    # Standard resolve includes both
    all_tools = registry.resolve(no_builtin_tools=False)
    tool_names = {t.name for t in all_tools}
    assert "built_in_meta_tool" in tool_names
    assert "custom_file_write" in tool_names

    # Pure domain resolve strips META tools
    pure_tools = registry.resolve(no_builtin_tools=True)
    pure_names = {t.name for t in pure_tools}
    assert "built_in_meta_tool" not in pure_names
    assert "custom_file_write" in pure_names
    assert len(pure_tools) == 1


def test_host_tool_sharing_a_built_in_name_stays_when_built_ins_are_left_out() -> None:
    registry = ToolRegistry()
    registry.register(built_in_meta_tool, source=ToolSource.META)
    registry.register(host_tool_named_like_a_built_in, source=ToolSource.USER)

    # Offered together, the built-in shadows the host tool by source priority.
    assert registry.resolve(no_builtin_tools=False) == [built_in_meta_tool]
    # Leaving the built-ins out must not take the host tool's name with them.
    assert registry.resolve(no_builtin_tools=True) == [host_tool_named_like_a_built_in]


def test_snapshot_lists_the_tools_resolve_offers_with_and_without_built_ins() -> None:
    registry = ToolRegistry()
    registry.register(built_in_meta_tool, source=ToolSource.META)
    registry.register(host_tool_named_like_a_built_in, source=ToolSource.USER)
    registry.register(custom_file_write, source=ToolSource.USER)

    for no_builtin_tools in (False, True):
        offered = [t.name for t in registry.resolve(no_builtin_tools=no_builtin_tools)]
        listed = [s.name for s in registry.snapshot(no_builtin_tools=no_builtin_tools)]
        assert listed == offered
