"""Integration: discoverable tool chain must not register OS browser history search."""

from __future__ import annotations

import pytest

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig


def _tool_names(items: list[object]) -> set[str]:
    return {name for tool in items if (name := getattr(tool, "name", None))}


@pytest.mark.asyncio
async def test_discoverable_chain_excludes_browser_local_search() -> None:
    """Mirrors factory.py tool-setup chain through cron (no LLM, no mock)."""
    agent = GeneralAgent(
        model_cfg=ModelConfig(model="test/model", api_key="test-key"),
        mcp_config=None,
        enable_web_search=True,
        enable_browser=True,
        enable_memory=False,
    )

    tools: list[object] = []
    discoverable_tools: list[object] = []
    agent._setup_search_and_basic_tools(tools, discoverable_tools)
    agent._setup_clarification_tools(tools, discoverable_tools)
    await agent._setup_cron_tools(tools, discoverable_tools, user_id="integration-user")

    all_names = _tool_names(tools) | _tool_names(discoverable_tools)
    assert "browser_local_search_tool" not in all_names
