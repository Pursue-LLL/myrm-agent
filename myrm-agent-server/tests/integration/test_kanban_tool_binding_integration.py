"""Kanban role-gate tool binding — integration (real KanbanService + SQLite store).

Exercises: KanbanService.get_instance → SqlAlchemyKanbanStore → _setup_kanban_tools
→ create_kanban_tools. No mocks on store or tool binding. Agent validation bypass
only (_validate_agent_id), consistent with other kanban integration tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.types import ModelConfig
from app.services.kanban import KanbanService

ORCHESTRATOR_TOOL_NAMES = frozenset(
    {
        "kanban_add_task",
        "kanban_list_tasks",
        "kanban_update_task",
        "kanban_move_task",
        "kanban_delete_task",
        "kanban_board_summary",
        "kanban_add_dependency",
        "kanban_remove_dependency",
    }
)

WORKER_TOOL_NAMES = frozenset(
    {
        "kanban_show",
        "kanban_complete",
        "kanban_block",
        "kanban_heartbeat",
        "kanban_comment",
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
async def test_real_service_chat_binds_eight_orchestrator_tools() -> None:
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
    assert len(tools) == 8
    assert bound_names == set(ORCHESTRATOR_TOOL_NAMES)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_service_task_bound_binds_five_worker_tools() -> None:
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
    assert len(tools) == 5
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
async def test_full_mode_opt_in_binds_sixteen_tools_on_real_store() -> None:
    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    await svc.create_board("Full Mode Board")

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="full",
        kanban_current_task_id=None,
        agent_id="agent-integ-full",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    bound_names = {getattr(tool, "name", None) for tool in tools}
    assert len(tools) == 16
    assert ORCHESTRATOR_TOOL_NAMES.issubset(bound_names)
    assert WORKER_TOOL_NAMES.issubset(bound_names)


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
