"""Unit tests for Kanban task handoff and assignee transition tracking.

[INPUT] move_task invocations with assignee_agent_id and handoff metadata.
[OUTPUT] Verified agent_id migration, handoff metadata payload, and handoff_history accumulation.
[POS] tests/services/kanban/test_kanban_handoff.py
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask, TaskStatus

from app.services.kanban.move_orchestrator import move_task


def _make_task(task_id: str = "t-1", agent_id: str | None = "agent-developer") -> KanbanTask:
    return KanbanTask(
        task_id=task_id,
        board_id="b-1",
        title="Refactor auth module",
        status=TaskStatus.BACKLOG,
        agent_id=agent_id,
    )


def _make_store(task: KanbanTask) -> AsyncMock:
    store = AsyncMock()
    store.get_task.return_value = task
    store.get_board.return_value = KanbanBoard(board_id="b-1", name="Engineering Sprint")
    store.save_task.side_effect = lambda t: t
    store.are_dependencies_met.return_value = True
    return store


@pytest.mark.asyncio
async def test_move_task_with_assignee_handoff() -> None:
    task = _make_task(agent_id="agent-architect")
    store = _make_store(task)

    updated = await move_task(
        store,
        {},
        None,
        "t-1",
        TaskStatus.READY,
        result="Initial architecture spec completed",
        metadata={
            "changed_files": ["src/auth/service.py", "src/auth/jwt.py"],
            "note": "Please review token revocation and implement unit tests.",
        },
        assignee_agent_id="agent-developer",
        wake_dispatcher=lambda _board_id: None,
    )

    assert updated is not None
    # Agent ID updated
    assert updated.agent_id == "agent-developer"
    assert updated.status == TaskStatus.READY

    # Handoff metadata recorded
    handoff = updated.metadata.get("handoff")
    assert isinstance(handoff, dict)
    assert handoff["from_agent_id"] == "agent-architect"
    assert handoff["to_agent_id"] == "agent-developer"
    assert handoff["summary"] == "Initial architecture spec completed"
    assert handoff["changed_files"] == ["src/auth/service.py", "src/auth/jwt.py"]
    assert "timestamp" in handoff

    # Handoff history recorded
    history = updated.metadata.get("handoff_history")
    assert isinstance(history, list)
    assert len(history) == 1
    assert history[0]["from_agent_id"] == "agent-architect"
    assert history[0]["to_agent_id"] == "agent-developer"


@pytest.mark.asyncio
async def test_multiple_consecutive_handoffs_accumulate_history() -> None:
    task = _make_task(agent_id="agent-pm")
    store = _make_store(task)

    # First handoff: PM -> Architect
    task_step1 = await move_task(
        store,
        {},
        None,
        "t-1",
        TaskStatus.READY,
        result="Requirements specified",
        metadata={"spec_url": "/specs/auth.md"},
        assignee_agent_id="agent-architect",
        wake_dispatcher=lambda _board_id: None,
    )
    assert task_step1 is not None
    assert task_step1.agent_id == "agent-architect"

    # Second handoff: Architect -> QA
    store.get_task.return_value = task_step1
    task_step2 = await move_task(
        store,
        {},
        None,
        "t-1",
        TaskStatus.READY,
        result="Design ready for test plan",
        metadata={"test_cases": ["login", "token_refresh"]},
        assignee_agent_id="agent-qa",
        wake_dispatcher=lambda _board_id: None,
    )

    assert task_step2 is not None
    assert task_step2.agent_id == "agent-qa"
    history = task_step2.metadata.get("handoff_history")
    assert isinstance(history, list)
    assert len(history) == 2
    assert history[0]["from_agent_id"] == "agent-pm"
    assert history[0]["to_agent_id"] == "agent-architect"
    assert history[1]["from_agent_id"] == "agent-architect"
    assert history[1]["to_agent_id"] == "agent-qa"
