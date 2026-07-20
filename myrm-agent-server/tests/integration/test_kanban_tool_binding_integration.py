"""Kanban role-gate tool binding — integration (real KanbanService + SQLite store).

Exercises: KanbanService.get_instance → SqlAlchemyKanbanStore → _setup_kanban_tools
→ create_kanban_tools. No mocks on store or tool binding. Agent validation bypass
only (_validate_agent_id), consistent with other kanban integration tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.types import ModelConfig
from app.services.kanban import KanbanService

ORCHESTRATOR_TOOL_NAMES = frozenset(
    {
        "kanban_add_task",
        "kanban_list_tasks",
        "kanban_unblock",
    }
)

WORKER_TOOL_NAMES = frozenset(
    {
        "kanban_show",
        "kanban_complete",
        "kanban_block",
        "kanban_heartbeat",
        "kanban_comment",
        "kanban_attach",
    }
)


@pytest.fixture(autouse=True)
def _reset_kanban_singleton() -> None:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


def _minimal_model_cfg() -> ModelConfig:
    return ModelConfig(model="openai/gpt-4o-mini", api_key="test-key")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_service_chat_binds_three_orchestrator_tools() -> None:
    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    await svc.create_board("Role Gate Chat Board")

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id=None,
        agent_id="agent-integ-chat",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    bound_names = {getattr(tool, "name", None) for tool in tools}
    assert len(tools) == 3
    assert bound_names == set(ORCHESTRATOR_TOOL_NAMES)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_service_task_bound_binds_six_worker_tools() -> None:
    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    board = await svc.create_board("Role Gate Worker Board")
    task = await svc.add_task(
        board.board_id,
        "Worker integration task",
        agent_id="agent-integ-worker",
    )

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="worker",
        kanban_current_task_id=task.task_id,
        agent_id="agent-integ-worker",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    bound_names = {getattr(tool, "name", None) for tool in tools}
    assert len(tools) == 6
    assert bound_names == set(WORKER_TOOL_NAMES)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_id_overrides_orchestrator_mode_on_real_store() -> None:
    """TaskRunner path: kanban_current_task_id forces worker even if mode says orchestrator."""
    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    board = await svc.create_board("Override Board")
    task = await svc.add_task(board.board_id, "Override task")

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id=task.task_id,
        agent_id="agent-integ-override",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    bound_names = {getattr(tool, "name", None) for tool in tools}
    assert bound_names == set(WORKER_TOOL_NAMES)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_legacy_full_mode_falls_back_to_orchestrator_tools() -> None:
    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    await svc.create_board("Legacy Full Board")

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="full",
        kanban_current_task_id=None,
        agent_id="agent-integ-full",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    bound_names = {getattr(tool, "name", None) for tool in tools}
    assert len(tools) == 3
    assert bound_names == set(ORCHESTRATOR_TOOL_NAMES)


@pytest.mark.integration
def test_agent_factory_default_kanban_tool_mode_is_orchestrator() -> None:
    params = GeneralAgentParams(
        query="integration probe",
        model_cfg=_minimal_model_cfg(),
        enable_kanban=True,
    )
    agent = AgentFactory.create_general_agent(params)
    assert agent.kanban_tool_mode == "orchestrator"
    assert agent.kanban_current_task_id is None


@pytest.mark.integration
def test_default_profile_excludes_kanban_from_auto_bind() -> None:
    from app.services.agent.profile_resolver import (
        DEFAULT_ENABLED_BUILTIN_TOOLS,
        resolve_builtin_tool_flags,
    )

    assert "kanban" not in DEFAULT_ENABLED_BUILTIN_TOOLS
    flags = resolve_builtin_tool_flags(list(DEFAULT_ENABLED_BUILTIN_TOOLS))
    assert flags["enable_kanban"] is False


@pytest.mark.integration
def test_task_runner_params_pattern_forces_worker_mode() -> None:
    from app.services.agent.profile_resolver import resolve_builtin_tool_flags

    flags = resolve_builtin_tool_flags(["web_search", "memory", "kanban"])
    params = GeneralAgentParams(
        query="kanban task context",
        model_cfg=_minimal_model_cfg(),
        kanban_tool_mode="worker",
        kanban_current_task_id="task-runner-1",
        **flags,
    )
    agent = AgentFactory.create_general_agent(params)
    assert agent.kanban_tool_mode == "worker"
    assert agent.kanban_current_task_id == "task-runner-1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_whitespace_mode_falls_back_to_orchestrator_tools() -> None:
    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    await svc.create_board("Invalid Mode Board")

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="  not-a-real-mode  ",
        kanban_current_task_id=None,
        agent_id="agent-integ-invalid",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    bound_names = {getattr(tool, "name", None) for tool in tools}
    assert len(tools) == 3
    assert bound_names == set(ORCHESTRATOR_TOOL_NAMES)


@pytest.mark.integration
def test_kanban_in_enabled_builtin_tools_maps_enable_kanban() -> None:
    from app.services.agent.profile_resolver import resolve_builtin_tool_flags

    flags = resolve_builtin_tool_flags(["web_search", "memory", "kanban"])
    assert flags["enable_kanban"] is True

    agent = AgentFactory.create_general_agent(
        GeneralAgentParams(
            query="flag probe",
            model_cfg=_minimal_model_cfg(),
            **flags,
        )
    )
    assert agent.enable_kanban is True
    assert agent.kanban_tool_mode == "orchestrator"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_list_tasks_by_task_id_on_real_store() -> None:
    """End-to-end: real SQLite store → _setup_kanban_tools → list_tasks(task_id=)."""
    import json

    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    board = await svc.create_board("List By Id Board")
    parent = await svc.add_task(board.board_id, "Parent task")
    child = await svc.add_task(board.board_id, "Child task")
    await svc.store.add_edge(parent.task_id, child.task_id)

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id=None,
        agent_id="agent-integ-list-id",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    list_tool = next(t for t in tools if getattr(t, "name", None) == "kanban_list_tasks")
    raw = await list_tool.ainvoke({"task_id": child.task_id})
    data = json.loads(raw)

    assert data["count"] == 1
    assert data["tasks"][0]["task_id"] == child.task_id
    assert data["parents"] == [parent.task_id]
    assert data["dependencies_met"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_list_tasks_include_stats_on_real_store() -> None:
    """End-to-end: list_tasks(include_stats=true) returns board counts."""
    import json

    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    board = await svc.create_board("Stats Board")
    await svc.add_task(board.board_id, "Ready task")
    blocked = await svc.add_task(board.board_id, "Blocked task")
    blocked_task = await svc.get_task(blocked.task_id)
    assert blocked_task is not None
    blocked_task.status = TaskStatus.BLOCKED
    blocked_task.blocked_reason = "hold"
    await svc.store.save_task(blocked_task)

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id=None,
        agent_id="agent-integ-stats",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    list_tool = next(t for t in tools if getattr(t, "name", None) == "kanban_list_tasks")
    raw = await list_tool.ainvoke({"board_id": board.board_id, "include_stats": True})
    data = json.loads(raw)

    assert data["total_tasks"] >= 2
    assert "task_counts" in data
    assert data["board"]["board_id"] == board.board_id
