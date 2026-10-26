"""Tests for extensible leaf-blocked tool registration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.deep_research.config import DeepResearchConfig
from myrm_agent_harness.agent.deep_research.helpers import build_research_subagent_config
from myrm_agent_harness.agent.sub_agents.builder import filter_tools
from myrm_agent_harness.agent.sub_agents.delegation_policy import (
    register_leaf_blocked_tools,
)
from myrm_agent_harness.agent.sub_agents.types import (
    DELEGATION_CAPABILITY_MANIFEST,
    MemoryIsolationPolicy,
    SubagentConfig,
)

_MEMORY_WRITE_TOOLS = ("memory_save_tool", "memory_manage_tool")


def _tools(*names: str) -> list[MagicMock]:
    tools = []
    for name in names:
        tool = MagicMock()
        tool.name = name
        tools.append(tool)
    return tools


def test_delegation_manifest_blocks_ask_question_tool() -> None:
    assert "ask_question_tool" in DELEGATION_CAPABILITY_MANIFEST.leaf_blocked_tools


def test_register_leaf_blocked_tools_filters_subagent_tools() -> None:
    register_leaf_blocked_tools(frozenset({"channel_notify_tool"}))

    filtered = filter_tools(SubagentConfig(system_prompt="test"), _tools("web_search_tool", "channel_notify_tool"))
    filtered_names = {tool.name for tool in filtered}

    assert "web_search_tool" in filtered_names
    assert "channel_notify_tool" not in filtered_names


def test_register_leaf_blocked_tools_noop_on_empty() -> None:
    from myrm_agent_harness.agent.sub_agents.delegation_policy import (
        get_effective_leaf_blocked_tools,
    )
    from myrm_agent_harness.agent.sub_agents.types import DELEGATION_CAPABILITY_MANIFEST

    before = get_effective_leaf_blocked_tools(DELEGATION_CAPABILITY_MANIFEST.leaf_blocked_tools)
    register_leaf_blocked_tools(frozenset())
    after = get_effective_leaf_blocked_tools(DELEGATION_CAPABILITY_MANIFEST.leaf_blocked_tools)
    assert after == before


def test_delegation_manifest_blocks_memory_write_tools() -> None:
    assert set(_MEMORY_WRITE_TOOLS) <= DELEGATION_CAPABILITY_MANIFEST.leaf_blocked_tools


@pytest.mark.parametrize("policy", list(MemoryIsolationPolicy))
def test_child_never_inherits_memory_write_tools_under_any_isolation_policy(policy: MemoryIsolationPolicy) -> None:
    """The parent's memory tools are bound to the parent's manager; no isolation policy can rebind them."""
    config = SubagentConfig(system_prompt="test", memory_isolation=policy)

    kept = {tool.name for tool in filter_tools(config, _tools("memory_search_tool", *_MEMORY_WRITE_TOOLS))}

    assert kept == {"memory_search_tool"}


def test_explicit_allowlist_cannot_re_enable_memory_write_tools() -> None:
    config = SubagentConfig(system_prompt="test", tools=("memory_search_tool", *_MEMORY_WRITE_TOOLS))

    kept = {tool.name for tool in filter_tools(config, _tools("memory_search_tool", *_MEMORY_WRITE_TOOLS))}

    assert kept == {"memory_search_tool"}


def test_deep_research_children_never_inherit_memory_write_tools() -> None:
    """Deep research builds its children through filter_tools alone, so only the L1 blocklist protects it."""
    config = build_research_subagent_config(DeepResearchConfig())

    kept = {tool.name for tool in filter_tools(config, _tools("web_search_tool", *_MEMORY_WRITE_TOOLS))}

    assert kept == {"web_search_tool"}
