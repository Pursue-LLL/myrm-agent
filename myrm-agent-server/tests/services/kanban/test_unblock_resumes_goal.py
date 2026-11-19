"""Unblocking a goal-mode task puts its parked goal back to work.

The task's goal lives under the session key `kanban:<task id>`. Unblocking happens outside any run, so it reaches the goal
through storage and must not leave a provider registered for that session: the task runner registers one for each run and
takes it back when the run ends.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask, TaskStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.kanban.move_orchestrator import move_task

_BOARD_ID = "b1"
_TASK_ID = "t1"
_SESSION = f"kanban:{_TASK_ID}"


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parked_as", [GoalStatus.PAUSED, GoalStatus.WAIT, GoalStatus.NEEDS_HUMAN_REVIEW, GoalStatus.BUDGET_LIMITED]
)
async def test_unblocking_resumes_the_parked_goal_and_leaves_no_provider_registered(parked_as: GoalStatus) -> None:
    store = InMemoryKanbanStore()
    await store.save_board(KanbanBoard(board_id=_BOARD_ID, name="Board"))
    await store.save_task(
        KanbanTask(task_id=_TASK_ID, board_id=_BOARD_ID, title="Goal task", status=TaskStatus.BLOCKED, goal_mode=True)
    )
    provider = GoalRegistry.resolve_provider(_SESSION)
    goal = await provider.create_goal(_SESSION, "Ship the report")
    await provider.update_status(goal.goal_id, parked_as)

    moved = await move_task(store, {}, None, _TASK_ID, TaskStatus.READY, wake_dispatcher=lambda _board_id: None)

    assert moved is not None
    assert moved.status is TaskStatus.READY
    stored = await provider.get_goal(goal.goal_id)
    assert stored is not None
    assert stored.status is GoalStatus.ACTIVE
    assert GoalRegistry.get_provider(_SESSION) is None
