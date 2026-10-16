"""A card that leaves the blocked column takes its block details with it.

[INPUT]
- myrm_agent_harness InMemoryKanbanStore (POS: the store the real dispatcher tests run against)
- app.services.kanban.move_orchestrator::move_task (POS: the manual or agent-initiated move between columns)
- app.services.kanban.event_publisher (POS: the SSE payload every user-facing consumer reads)

[OUTPUT]
Pins that the reason, the kind and the wake-up time of a block exist only while the task is blocked: whichever
column a blocked card is moved to, none of the three stays on it, so a card in another column neither shows a
reason it no longer has nor a countdown to a wake-up that never comes, and blocking it again without a reason does
not announce the old one. Re-blocking an already blocked card keeps its reason.

[POS]
tests/services/kanban/test_move_task_block_fields.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import BlockKind, KanbanBoard, KanbanTask, TaskStatus

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban import event_publisher
from app.services.kanban.move_orchestrator import move_task

BOARD_ID = "b1"
TASK_ID = "t1"
BLOCK_REASON = "Need your decision: use Postgres or SQLite for the report store?"


async def _blocked_task_store(block_kind: BlockKind = BlockKind.HUMAN) -> InMemoryKanbanStore:
    store = InMemoryKanbanStore()
    await store.save_board(KanbanBoard(board_id=BOARD_ID, name="Board"))
    await store.save_task(
        KanbanTask(
            task_id=TASK_ID,
            board_id=BOARD_ID,
            title="Blocked task",
            status=TaskStatus.BLOCKED,
            block_kind=block_kind,
            blocked_reason=BLOCK_REASON,
            scheduled_until=datetime.now(UTC) + timedelta(minutes=15) if block_kind is BlockKind.SCHEDULED else None,
        )
    )
    return store


async def _move(
    store: InMemoryKanbanStore,
    target: TaskStatus,
    *,
    block_kind: BlockKind | None = None,
    blocked_reason: str | None = None,
    scheduled_until: datetime | None = None,
) -> tuple[KanbanTask, list[dict[str, str]]]:
    """Move the task and return it with the payload of every task event the move published."""
    with patch.object(event_publisher, "get_event_bus") as get_bus:
        moved = await move_task(
            # The in-memory store is the same store the real dispatcher tests run against; only its type differs.
            cast(SqlAlchemyKanbanStore, store),
            {},
            None,
            TASK_ID,
            target,
            block_kind=block_kind,
            blocked_reason=blocked_reason,
            scheduled_until=scheduled_until,
            wake_dispatcher=lambda _board_id: None,
        )
    assert moved is not None
    return moved, [call.args[0].data for call in get_bus.return_value.publish.call_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize("block_kind", [BlockKind.HUMAN, BlockKind.SCHEDULED, BlockKind.EXTERNAL])
@pytest.mark.parametrize(
    "target",
    [TaskStatus.BACKLOG, TaskStatus.READY, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED],
)
async def test_a_card_moved_out_of_the_blocked_column_keeps_no_block_details(target: TaskStatus, block_kind: BlockKind) -> None:
    store = await _blocked_task_store(block_kind)

    moved, _ = await _move(store, target)

    assert moved.status is target
    assert (moved.blocked_reason, moved.block_kind, moved.scheduled_until) == (None, None, None)
    stored = await store.get_task(TASK_ID)
    assert stored is not None
    assert (stored.blocked_reason, stored.block_kind, stored.scheduled_until) == (None, None, None)


@pytest.mark.asyncio
async def test_blocking_a_card_again_without_a_reason_does_not_announce_the_old_one() -> None:
    store = await _blocked_task_store()
    await _move(store, TaskStatus.BACKLOG)

    moved, published = await _move(store, TaskStatus.BLOCKED)

    assert moved.blocked_reason is None
    assert "detail" not in published[-1]
    assert BLOCK_REASON not in str(published)


@pytest.mark.asyncio
async def test_blocking_a_card_again_with_a_reason_reports_that_reason() -> None:
    store = await _blocked_task_store()
    await _move(store, TaskStatus.BACKLOG)

    moved, published = await _move(store, TaskStatus.BLOCKED, blocked_reason="Waiting for the client")

    assert moved.blocked_reason == "Waiting for the client"
    assert published[-1]["detail"] == "Waiting for the client"


@pytest.mark.asyncio
async def test_rescheduling_a_blocked_card_keeps_its_reason() -> None:
    store = await _blocked_task_store()
    wake_at = datetime.now(UTC) + timedelta(hours=2)

    moved, _ = await _move(store, TaskStatus.BLOCKED, block_kind=BlockKind.SCHEDULED, scheduled_until=wake_at)

    assert moved.status is TaskStatus.BLOCKED
    assert moved.blocked_reason == BLOCK_REASON
    assert (moved.block_kind, moved.scheduled_until) == (BlockKind.SCHEDULED, wake_at)
