"""Only a blocked task stores a block's reason, kind and wake-up time.

[INPUT]
- app.core.kanban.adapters.sqlalchemy_mapping::task_to_model, apply_task_to_model (POS: how a task is written to its row)
- myrm_agent_harness.toolkits.kanban.types (POS: the task, its statuses and block kinds)

[OUTPUT]
Pins that a row never stores block details for a task outside the blocked column, whichever code path set the task's
status: a task created with them or saved over an existing row gets none of them unless it is blocked.

[POS]
tests/core/kanban/test_task_mapping_block_details.py
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from myrm_agent_harness.toolkits.kanban.types import BlockKind, KanbanTask, TaskStatus

from app.core.kanban.adapters.sqlalchemy_mapping import apply_task_to_model, task_to_model
from app.database.models.kanban import KanbanTaskModel

_REASON = "Need your decision: Postgres or SQLite?"
_WAKE_AT = datetime(2030, 1, 1, 3, tzinfo=UTC)


def _task(status: TaskStatus) -> KanbanTask:
    return KanbanTask(
        task_id="t1",
        board_id="b1",
        title="Task",
        status=status,
        block_kind=BlockKind.SCHEDULED,
        blocked_reason=_REASON,
        scheduled_until=_WAKE_AT,
    )


def _stored(row: KanbanTaskModel) -> tuple[str | None, str | None, datetime | None]:
    return row.blocked_reason, row.block_kind, row.scheduled_until


@pytest.mark.parametrize("status", list(TaskStatus))
def test_a_new_row_stores_block_details_only_for_a_blocked_task(status: TaskStatus) -> None:
    expected = (_REASON, "scheduled", _WAKE_AT) if status is TaskStatus.BLOCKED else (None, None, None)

    assert _stored(task_to_model(_task(status))) == expected


@pytest.mark.parametrize("status", list(TaskStatus))
def test_saving_over_a_row_replaces_its_block_details_only_for_a_blocked_task(status: TaskStatus) -> None:
    row = KanbanTaskModel(id="t1", board_id="b1", title="Task", status="blocked", blocked_reason="old", block_kind="human")
    expected = (_REASON, "scheduled", _WAKE_AT) if status is TaskStatus.BLOCKED else (None, None, None)

    apply_task_to_model(_task(status), row)

    assert _stored(row) == expected
