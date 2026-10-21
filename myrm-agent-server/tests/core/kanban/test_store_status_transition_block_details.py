"""SqlAlchemyKanbanStore.transition_task_status keeps block details only for a task that ends up blocked.

[INPUT]
- app.core.kanban.adapters.sqlalchemy_store::SqlAlchemyKanbanStore (POS: the status-flip primitive over the real SQLite schema)
- myrm_agent_harness.toolkits.kanban.types (POS: the task, its statuses and block kinds)

[OUTPUT]
Pins that flipping the status of a blocked task through the primitive leaves the row without the block's reason, kind
and wake-up time unless the new status is blocked, in the returned task and in the stored row alike.

[POS]
tests/core/kanban/test_store_status_transition_block_details.py
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.kanban.types import BlockKind, KanbanBoard, KanbanTask, TaskStatus

from app.core.kanban.adapters.sqlalchemy_store import SqlAlchemyKanbanStore

_REASON = "Waiting for the client's answer"
_WAKE_AT = datetime(2099, 1, 1, 3, tzinfo=UTC)


@pytest_asyncio.fixture
async def store() -> AsyncIterator[SqlAlchemyKanbanStore]:
    yield SqlAlchemyKanbanStore()


@pytest_asyncio.fixture
async def board_id(store: SqlAlchemyKanbanStore) -> AsyncIterator[str]:
    board = await store.save_board(KanbanBoard(board_id=f"board-{uuid.uuid4().hex}", name="Status flip"))
    yield board.board_id
    await store.delete_board(board.board_id)


def _details(task: KanbanTask) -> tuple[str | None, BlockKind | None, datetime | None]:
    """SQLite hands datetimes back without a timezone, so the wake-up time is compared as wall-clock UTC."""
    wake_at = task.scheduled_until.replace(tzinfo=None) if task.scheduled_until else None
    return task.blocked_reason, task.block_kind, wake_at


@pytest.mark.asyncio
@pytest.mark.parametrize("new_status", list(TaskStatus))
async def test_flipping_a_blocked_task_keeps_block_details_only_when_it_stays_blocked(
    store: SqlAlchemyKanbanStore, board_id: str, new_status: TaskStatus
) -> None:
    task = await store.save_task(
        KanbanTask(
            task_id=f"task-{uuid.uuid4().hex}",
            board_id=board_id,
            title="Weekly digest",
            status=TaskStatus.BLOCKED,
            block_kind=BlockKind.SCHEDULED,
            blocked_reason=_REASON,
            scheduled_until=_WAKE_AT,
        )
    )
    kept = (_REASON, BlockKind.SCHEDULED, _WAKE_AT.replace(tzinfo=None))
    expected = kept if new_status is TaskStatus.BLOCKED else (None, None, None)

    moved = await store.transition_task_status(task.task_id, TaskStatus.BLOCKED, new_status)

    assert moved is not None
    assert moved.status is new_status
    assert _details(moved) == expected
    stored = await store.get_task(task.task_id)
    assert stored is not None
    assert _details(stored) == expected
