"""[INPUT]
- sqlalchemy (POS: SQL 表达式与结果类型)

[OUTPUT]
- TaskCardStats / BoardEventRow / _exec_rowcount

[POS]
Shared value types and the rowcount helper of the SQLAlchemy kanban store.
"""

from __future__ import annotations

from typing import NamedTuple, TypedDict


class TaskCardStats(NamedTuple):
    """Per-task aggregate stats for card badges."""

    dep_count: int
    children_total: int
    children_done: int
    comment_count: int


class BoardEventRow(TypedDict):
    """A board-level event with the title and assignee of its task."""

    event_id: int
    task_id: str
    task_title: str
    task_assignee: str
    kind: str
    payload: dict[str, object] | None
    run_id: str | None
    created_at: str


def _exec_rowcount(result: object) -> int:
    rc = getattr(result, "rowcount", None)
    return rc if isinstance(rc, int) else 0
