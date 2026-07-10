"""Factory kanban tool binding integration tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.ai_agents.general_agent.kanban_tool_mode import resolve_kanban_tool_mode

ORCHESTRATOR_TOOL_NAMES = frozenset(
    {
        "kanban_add_task",
        "kanban_list_tasks",
        "kanban_update_task",
        "kanban_move_task",
        "kanban_delete_task",
        "kanban_board_summary",
        "kanban_link",
    }
)


def _should_append_worker_lifecycle_guidance(agent_wrapper: object) -> bool:
    """Mirror general_agent/factory.py worker lifecycle prompt gate."""
    return (
        resolve_kanban_tool_mode(
            kanban_tool_mode=getattr(agent_wrapper, "kanban_tool_mode", None),
            kanban_current_task_id=getattr(agent_wrapper, "kanban_current_task_id", None),
        )
        == "worker"
    )


def test_worker_lifecycle_prompt_gate_follows_task_id() -> None:
    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id="task-abc",
    )
    assert _should_append_worker_lifecycle_guidance(agent_wrapper) is True


def test_worker_lifecycle_prompt_gate_skips_chat_orchestrator() -> None:
    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id=None,
    )
    assert _should_append_worker_lifecycle_guidance(agent_wrapper) is False


@pytest.mark.asyncio
async def test_setup_kanban_tools_chat_binds_seven_orchestrator_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore

    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    store = InMemoryKanbanStore()
    kanban_svc = MagicMock()
    kanban_svc.store = store
    kanban_svc._dispatchers = {}

    monkeypatch.setattr(
        "app.services.kanban.service.KanbanService.get_instance",
        lambda: kanban_svc,
    )

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id=None,
        agent_id="agent-test",
    )
    tools: list[object] = []

    await _setup_kanban_tools(agent_wrapper, tools)

    bound_names = {getattr(tool, "name", None) for tool in tools}
    assert len(tools) == 7
    assert bound_names == set(ORCHESTRATOR_TOOL_NAMES)


@pytest.mark.asyncio
async def test_resolve_kanban_default_board_id_prefers_valid_preferred() -> None:
    from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
    from myrm_agent_harness.toolkits.kanban.types import KanbanBoard

    from app.ai_agents.general_agent.factory import _resolve_kanban_default_board_id

    store = InMemoryKanbanStore()
    await store.save_board(KanbanBoard(board_id="board-a", name="A"))
    await store.save_board(KanbanBoard(board_id="board-b", name="B"))

    assert await _resolve_kanban_default_board_id(store, preferred_board_id="board-a") == "board-a"
    assert await _resolve_kanban_default_board_id(store, preferred_board_id="stale") is None


@pytest.mark.asyncio
async def test_resolve_kanban_default_board_id_invalid_preferred_does_not_fallback_newest() -> None:
    from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
    from myrm_agent_harness.toolkits.kanban.types import KanbanBoard

    from app.ai_agents.general_agent.factory import _resolve_kanban_default_board_id

    store = InMemoryKanbanStore()
    await store.save_board(KanbanBoard(board_id="board-newest", name="New"))
    await store.save_board(KanbanBoard(board_id="board-other", name="Other"))

    assert await _resolve_kanban_default_board_id(store, preferred_board_id="gone") is None
    assert await _resolve_kanban_default_board_id(store, preferred_board_id=None) == "board-newest"


@pytest.mark.asyncio
async def test_setup_kanban_tools_task_bound_binds_five_worker_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore

    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    store = InMemoryKanbanStore()
    kanban_svc = MagicMock()
    kanban_svc.store = store
    kanban_svc._dispatchers = {}

    monkeypatch.setattr(
        "app.services.kanban.service.KanbanService.get_instance",
        lambda: kanban_svc,
    )

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id="task-worker-1",
        agent_id="agent-test",
    )
    tools: list[object] = []

    await _setup_kanban_tools(agent_wrapper, tools)

    bound_names = {getattr(tool, "name", None) for tool in tools}
    assert len(tools) == 5
    assert bound_names == {
        "kanban_show",
        "kanban_complete",
        "kanban_block",
        "kanban_heartbeat",
        "kanban_comment",
    }
