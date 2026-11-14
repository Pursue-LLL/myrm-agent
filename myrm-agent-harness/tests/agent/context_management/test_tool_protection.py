"""Tests for the tool protection sets: each name in them is a tool the agent can call, and the default configuration protects the memory search tool."""

from __future__ import annotations

from collections.abc import Collection

import pytest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.context_management.infra.schemas import ToolProtectionConfig
from myrm_agent_harness.agent.context_management.infra.schemas.tool_protection import (
    BUILTIN_ACTIVE_PRUNE_NEVER_TOOLS,
    BUILTIN_FILTER_PROTECTED_TOOLS,
    DEFAULT_BUSINESS_PROTECTED_TOOLS,
    DEFAULT_SOFT_ONLY_TOOLS,
)
from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.filter_processor import FilterProcessor
from myrm_agent_harness.agent.tool_management.tool_layers import is_registered_action_tool

PROTECTION_SETS: dict[str, Collection[str]] = {
    "BUILTIN_FILTER_PROTECTED_TOOLS": BUILTIN_FILTER_PROTECTED_TOOLS,
    "BUILTIN_ACTIVE_PRUNE_NEVER_TOOLS": BUILTIN_ACTIVE_PRUNE_NEVER_TOOLS,
    "DEFAULT_BUSINESS_PROTECTED_TOOLS": DEFAULT_BUSINESS_PROTECTED_TOOLS,
    "DEFAULT_SOFT_ONLY_TOOLS": DEFAULT_SOFT_ONLY_TOOLS,
}

MEMORY_SEARCH_TOOL = "memory_search_tool"


@pytest.mark.parametrize("set_name", sorted(PROTECTION_SETS))
def test_every_name_in_a_protection_set_is_a_registered_tool(set_name: str) -> None:
    """The check is by exact name, so a name no tool carries protects nothing and nothing reports it."""
    unregistered = sorted(name for name in PROTECTION_SETS[set_name] if not is_registered_action_tool(name))

    assert unregistered == []


def test_the_default_configuration_protects_the_memory_search_tool_on_every_prune_path() -> None:
    config = ToolProtectionConfig.default()

    assert config.is_filter_protected(MEMORY_SEARCH_TOOL)
    assert config.is_active_prune_never(MEMORY_SEARCH_TOOL)
    assert config.prune_mode(MEMORY_SEARCH_TOOL) == "protect"


@pytest.mark.asyncio
async def test_a_large_memory_search_result_is_not_filtered() -> None:
    result_text = "memory " * 25_000
    context = ProcessorContext(
        messages=[ToolMessage(content=result_text, tool_call_id="call-1", name=MEMORY_SEARCH_TOOL)],
        user_query="test",
        llm=None,
    )

    result = await FilterProcessor().process(context)

    assert result.messages[0].content == result_text
    assert any("protected_tools" in operation for operation in result.operations)
