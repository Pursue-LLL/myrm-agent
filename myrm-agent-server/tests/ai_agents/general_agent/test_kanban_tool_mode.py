"""Kanban tool mode defaults and resolution for GeneralAgent factory."""

from app.ai_agents.agents import GeneralAgentParams
from app.ai_agents.general_agent.kanban_tool_mode import resolve_kanban_tool_mode


def test_general_agent_params_default_kanban_tool_mode_is_orchestrator() -> None:
    field = GeneralAgentParams.model_fields["kanban_tool_mode"]
    assert field.default == "orchestrator"


def test_resolve_kanban_tool_mode_task_bound_is_worker() -> None:
    assert (
        resolve_kanban_tool_mode(
            kanban_tool_mode="orchestrator",
            kanban_current_task_id="task-abc",
        )
        == "worker"
    )


def test_resolve_kanban_tool_mode_chat_default_is_orchestrator() -> None:
    assert (
        resolve_kanban_tool_mode(
            kanban_tool_mode=None,
            kanban_current_task_id=None,
        )
        == "orchestrator"
    )


def test_resolve_kanban_tool_mode_full_is_opt_in() -> None:
    assert (
        resolve_kanban_tool_mode(
            kanban_tool_mode="full",
            kanban_current_task_id=None,
        )
        == "full"
    )


def test_resolve_kanban_tool_mode_invalid_falls_back_to_orchestrator() -> None:
    assert (
        resolve_kanban_tool_mode(
            kanban_tool_mode="invalid-mode",
            kanban_current_task_id=None,
        )
        == "orchestrator"
    )


def test_orchestrator_mode_binds_eight_tools() -> None:
    from myrm_agent_harness.toolkits.kanban import create_kanban_tools
    from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore

    mode = resolve_kanban_tool_mode(kanban_tool_mode=None, kanban_current_task_id=None)
    tools = create_kanban_tools(InMemoryKanbanStore(), mode=mode)
    assert len(tools) == 8
    assert {t.name for t in tools} == {
        "kanban_add_task",
        "kanban_list_tasks",
        "kanban_update_task",
        "kanban_move_task",
        "kanban_delete_task",
        "kanban_board_summary",
        "kanban_add_dependency",
        "kanban_remove_dependency",
    }
