import pytest
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.services.kanban.service import KanbanService


@pytest.mark.asyncio
async def test_update_active_tasks_branch_metadata(init_test_database):
    # 1. Create a board and tasks
    svc = KanbanService.get_instance()
    board = await svc.create_board(name="Test Board")

    # Task 1: Active (READY)
    task1 = await svc.add_task(board.board_id, title="Task 1")
    # Task 2: Active (BACKLOG)
    task2 = await svc.add_task(board.board_id, title="Task 2", depends_on=[task1.task_id])
    # Task 3: Inactive (COMPLETED)
    task3 = await svc.add_task(board.board_id, title="Task 3")
    await svc.move_task(task3.task_id, TaskStatus.COMPLETED)

    # 2. Update branch metadata for this specific board
    updated_count = await svc.update_active_tasks_branch_metadata(
        new_branch="feature-branch", old_branch="main", migrated=True, board_id=board.board_id
    )

    # Only task1 and task2 should be updated
    assert updated_count == 2

    # 3. Verify metadata
    t1 = await svc.get_task(task1.task_id)
    assert t1.metadata.get("branch") == "feature-branch"

    t2 = await svc.get_task(task2.task_id)
    assert t2.metadata.get("branch") == "feature-branch"

    t3 = await svc.get_task(task3.task_id)
    assert t3.metadata.get("branch") != "feature-branch"

    # 4. Verify events
    events1 = await svc.list_events(task1.task_id)
    assert any(e.kind == "branch_switched" and e.payload.get("to") == "feature-branch" for e in events1)

    events3 = await svc.list_events(task3.task_id)
    assert not any(e.kind == "branch_switched" for e in events3)
