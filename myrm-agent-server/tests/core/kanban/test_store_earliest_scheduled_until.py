"""SqlAlchemyKanbanStore.earliest_scheduled_until against the real SQLite schema.

Every time used here lies in the year 2099, so tasks left behind by other tests (which schedule within
hours of now) can never be the answer.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    KanbanBoard,
    KanbanTask,
    TaskPriority,
    TaskStatus,
)

from app.core.kanban.adapters.sqlalchemy_store import SqlAlchemyKanbanStore

_JAN = datetime(2099, 1, 1, tzinfo=UTC)
_JUN = datetime(2099, 6, 1, tzinfo=UTC)
_MAR_2098 = datetime(2098, 3, 1, tzinfo=UTC)


def _task(
    board_id: str,
    *,
    status: TaskStatus,
    block_kind: BlockKind | None,
    scheduled_until: datetime | None,
) -> KanbanTask:
    return KanbanTask(
        task_id=f"task-{uuid.uuid4().hex}",
        board_id=board_id,
        title="Weekly digest",
        status=status,
        priority=TaskPriority.NORMAL,
        block_kind=block_kind,
        scheduled_until=scheduled_until,
    )


@pytest_asyncio.fixture
async def store() -> AsyncIterator[SqlAlchemyKanbanStore]:
    store = SqlAlchemyKanbanStore()
    board = await store.save_board(KanbanBoard(board_id=f"board-{uuid.uuid4().hex}", name="Wake query"))
    scheduled = (TaskStatus.BLOCKED, BlockKind.SCHEDULED)
    await store.save_task(_task(board.board_id, status=scheduled[0], block_kind=scheduled[1], scheduled_until=_JUN))
    await store.save_task(_task(board.board_id, status=scheduled[0], block_kind=scheduled[1], scheduled_until=_JAN))
    # Not auto-unblocked by the clock: a human block with a stale time, and a task that left the block.
    await store.save_task(_task(board.board_id, status=TaskStatus.BLOCKED, block_kind=BlockKind.HUMAN, scheduled_until=_MAR_2098))
    await store.save_task(_task(board.board_id, status=TaskStatus.READY, block_kind=None, scheduled_until=_MAR_2098))
    yield store
    await store.delete_board(board.board_id)


@pytest.mark.asyncio
async def test_returns_the_earliest_future_scheduled_block(store: SqlAlchemyKanbanStore) -> None:
    """The human block and the READY task carry an earlier 2098 time; neither is released by the clock."""
    assert await store.earliest_scheduled_until(datetime(2098, 1, 1, tzinfo=UTC)) == _JAN


@pytest.mark.asyncio
async def test_only_times_strictly_after_the_reference_count(store: SqlAlchemyKanbanStore) -> None:
    assert await store.earliest_scheduled_until(_JAN) == _JUN
    assert await store.earliest_scheduled_until(datetime(2099, 7, 1, tzinfo=UTC)) is None
