"""Integration: UnifiedCapabilityDefer economics, discover hits, invoke proxy."""

from __future__ import annotations

import pytest
from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from myrm_agent_harness.agent.meta_tools.defer.invoke_deferred_tool import (
    INVOKE_DEFERRED_TOOL_NAME,
)
from myrm_agent_harness.agent.meta_tools.discover_capability.discover_capability_tool import (
    sync_discover_capability_tool,
)
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolBindMode, ToolSource
from myrm_agent_harness.backends.skills.types import SkillMetadata


class _DummyInput(BaseModel):
    arg1: str = Field(default="")


class _DummyDeferredTool(BaseTool):
    name: str = "dummy_deferred_tool"
    description: str = "Deferred placeholder for defer integration tests."
    args_schema: type[BaseModel] = _DummyInput

    def _run(self, arg1: str = "") -> str:
        return "ok"


@tool("bash_process_tool", description="Manage background bash processes")
def _bash_process_tool() -> str:
    return "listed"


def _searchable_skills() -> list[SkillMetadata]:
    return [
        SkillMetadata(
            name="defer_integration_skill",
            description="Enables discover gateway binding in DeferEconomics tests.",
        )
    ]


@pytest.mark.integration
def test_sync_economics_binds_invoke_not_discover_for_small_pool() -> None:
    registry = ToolRegistry()
    registry.register(_bash_process_tool, source=ToolSource.META, bind_mode=ToolBindMode.DISCOVERABLE)

    sync_discover_capability_tool(registry)

    assert registry.has_tool(INVOKE_DEFERRED_TOOL_NAME)
    assert not registry.has_tool("discover_capability_tool")


@pytest.mark.integration
def test_sync_economics_binds_discover_when_searchable_skills() -> None:
    registry = ToolRegistry()
    registry.register(_bash_process_tool, source=ToolSource.META, bind_mode=ToolBindMode.DISCOVERABLE)

    sync_discover_capability_tool(registry, skills=_searchable_skills())

    assert registry.has_tool(INVOKE_DEFERRED_TOOL_NAME)
    assert registry.has_tool("discover_capability_tool")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_native_hit_emits_deferred_tool_hits() -> None:
    registry = ToolRegistry()
    registry.register(_DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.DISCOVERABLE)
    discover = sync_discover_capability_tool(registry, skills=_searchable_skills())
    assert discover is not None

    result = await discover.ainvoke({"query": ".*", "mode": "regex"})
    assert "<DeferredToolHits>" in result
    assert "dummy_deferred_tool" in result
    assert "<AutoMountTools>" not in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invoke_deferred_executes_discoverable_tool() -> None:
    registry = ToolRegistry()
    registry.register(_bash_process_tool, source=ToolSource.META, bind_mode=ToolBindMode.DISCOVERABLE)
    sync_discover_capability_tool(registry)

    invoke = next(t for t in registry.resolve() if t.name == INVOKE_DEFERRED_TOOL_NAME)
    result = await invoke.ainvoke({"name": "bash_process_tool", "arguments": {}})
    assert result == "listed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_harness_build_tools_includes_invoke_for_discoverable_pool() -> None:
    from myrm_agent_harness.agent._internals._agent_build import build_tools

    registry = ToolRegistry()
    registry.register(_bash_process_tool, source=ToolSource.META, bind_mode=ToolBindMode.DISCOVERABLE)

    tools = await build_tools(registry, user_tools=[], discoverable_tools=[], cached_middlewares=[])
    names = {t.name for t in tools}
    assert INVOKE_DEFERRED_TOOL_NAME in names
    assert "discover_capability_tool" not in names
