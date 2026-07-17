"""Integration: discoverable tool chain must not register OS browser history search."""

from __future__ import annotations

import json
import re

import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig


def _tool_names(items: list[object]) -> set[str]:
    return {name for tool in items if (name := getattr(tool, "name", None))}


class _CronStubInput(BaseModel):
    action: str = Field(default="list")


class _CronStubTool(BaseTool):
    name: str = "cron_manage_tool"
    description: str = "Manage scheduled cron jobs for the agent."
    args_schema: type[BaseModel] = _CronStubInput

    def _run(self, action: str = "list") -> str:
        return action


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
    agent._setup_search_and_basic_tools(tools)
    agent._setup_clarification_tools(tools)
    await agent._setup_cron_tools(tools, user_id="integration-user")

    all_names = _tool_names(tools)
    assert "browser_local_search_tool" not in all_names


@pytest.mark.asyncio
async def test_discover_capability_does_not_surface_browser_local_search() -> None:
    """Edge: BM25 discover query for history/bookmarks must not resurrect removed tool."""
    from myrm_agent_harness.agent.meta_tools.discover_capability.discover_capability_tool import (
        create_discover_capability_tool,
    )
    from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
    from myrm_agent_harness.agent.tool_management.types import ToolBindMode, ToolSource

    registry = ToolRegistry()
    cron_tool = _CronStubTool()
    registry.register(
        cron_tool,
        source=ToolSource.META,
        bind_mode=ToolBindMode.TURN1,
    )

    discover_tool = create_discover_capability_tool(registry=registry, skills=[])

    result = await discover_tool.ainvoke({"query": "browser history bookmarks chrome local"})
    assert "browser_local_search_tool" not in result

    automount_match = re.search(r"<AutoMountTools>\n(.*?)\n</AutoMountTools>", result, re.DOTALL)
    if automount_match:
        mounted = json.loads(automount_match.group(1))
        mounted_names = {entry["name"] for entry in mounted}
        assert "browser_local_search_tool" not in mounted_names


@pytest.mark.asyncio
async def test_sandbox_deploy_mode_never_imports_local_browser_package() -> None:
    """Edge: SANDBOX mode — removed package must stay absent (no conditional import)."""
    import importlib.util

    spec = importlib.util.find_spec("app.services.local_browser")
    assert spec is None
