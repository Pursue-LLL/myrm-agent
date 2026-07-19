"""Tests for SubagentManagementExtension registry-based tool injection."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from app.ai_agents.extensions.subagent_extension import SubagentManagementExtension
from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.tool_management import ToolRegistry, ToolLifecycleManager

_SPAWN = "myrm_agent_harness.agent.meta_tools.spawn_subagent"
_MATERIALIZE = "app.ai_agents.general_agent.blueprint_materializer.materialize_jit_configs"
_CATALOG = "app.ai_agents.subagent_catalog.DatabaseSubagentCatalog"

_EXPECTED_TOOL_NAMES = (
    "delegate_task_tool",
    "subagent_control_tool",
)


def _make_tool(name: str) -> BaseTool:
    tool = MagicMock(spec=BaseTool)
    tool.name = name
    return tool


def _make_bare_agent() -> BaseAgent:
    agent = BaseAgent.__new__(BaseAgent)
    agent.llm = MagicMock()
    agent.fallback_llm = None
    agent.safety_fallback_llm = None
    agent.escalation_target_llm = None
    agent.executor = None
    agent.user_middlewares = []
    agent.system_prompt = "test"
    agent.user_tools = []
    agent.context_schema = None
    agent.config = MagicMock()
    agent.config.parallel_tool_calls = None
    agent.on_artifacts_ready = None
    agent.checkpointer = None
    agent.event_log_backend = None
    agent._agent = None
    agent._tool_registry = ToolRegistry()
    agent._cached_tools = None
    agent._cached_system_prompt = None
    agent._cached_middlewares = None
    agent._failover_used = False
    agent._last_run_stats = None
    agent._last_context = {}
    agent._subagent_manager = MagicMock()
    agent._is_running = False
    agent._extensions = []
    agent._tools_initialized = False
    agent._lifecycle_manager = ToolLifecycleManager()
    return agent


def _spawn_patches(*, list_available: list[str] | None = None) -> tuple[dict[str, MagicMock], list[tuple[str, object]]]:
    delegate_tool = _make_tool("delegate_task_tool")
    catalog_instance = MagicMock()
    catalog_instance.list_available = AsyncMock(return_value=list_available or ["research-agent"])
    created: dict[str, MagicMock] = {
        "delegate": MagicMock(return_value=delegate_tool),
        "control": MagicMock(return_value=_make_tool("subagent_control_tool")),
        "update_desc": AsyncMock(),
        "catalog": catalog_instance,
    }
    patch_specs: list[tuple[str, object]] = [
        (_MATERIALIZE, MagicMock(return_value={})),
        (_CATALOG, MagicMock(return_value=catalog_instance)),
        (f"{_SPAWN}.create_delegate_task_tool", created["delegate"]),
        (f"{_SPAWN}.create_subagent_control_tool", created["control"]),
        (f"{_SPAWN}.update_delegate_task_description", created["update_desc"]),
    ]
    return created, patch_specs


def _enter_spawn_patches(stack: ExitStack, *, list_available: list[str] | None = None) -> None:
    _, patch_specs = _spawn_patches(list_available=list_available)
    for target, replacement in patch_specs:
        stack.enter_context(patch(target, new=replacement))


@pytest.mark.asyncio
async def test_on_agent_init_registers_subagent_tools_on_registry() -> None:
    agent = _make_bare_agent()
    ext = SubagentManagementExtension(jit_subagents={}, subagent_ids=["research-agent"])

    with ExitStack() as stack:
        _enter_spawn_patches(stack)
        await ext.on_agent_init(agent)

    resolved_names = {tool.name for tool in agent._tool_registry.resolve()}
    assert set(_EXPECTED_TOOL_NAMES).issubset(resolved_names)


@pytest.mark.asyncio
async def test_subagent_extension_skips_bind_when_catalog_empty() -> None:
    agent = _make_bare_agent()
    ext = SubagentManagementExtension(jit_subagents={}, subagent_ids=[])

    with ExitStack() as stack:
        _enter_spawn_patches(stack, list_available=[])
        await ext.on_agent_init(agent)

    resolved_names = {tool.name for tool in agent._tool_registry.resolve()}
    assert "delegate_task_tool" not in resolved_names
    assert "subagent_control_tool" not in resolved_names


@pytest.mark.asyncio
async def test_subagent_extension_single_create_agent_on_init() -> None:
    agent = _make_bare_agent()
    agent.register_extension(SubagentManagementExtension(jit_subagents={}, subagent_ids=["research-agent"]))

    with ExitStack() as stack:
        _enter_spawn_patches(stack)
        stack.enter_context(patch.object(agent, "_build_middlewares", return_value=[]))
        stack.enter_context(patch.object(agent, "_build_tools", AsyncMock(return_value=[])))
        mock_create = stack.enter_context(patch("myrm_agent_harness.agent.base_agent.create_agent"))
        mock_create.return_value = MagicMock()
        await agent._ensure_initialized()

    assert mock_create.call_count == 1
    tool_names = {tool.name for tool in agent._cached_tools}
    assert "delegate_task_tool" in tool_names
