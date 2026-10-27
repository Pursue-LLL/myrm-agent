"""Validated list-query filters for the task store.

[INPUT]
- tasks.protocols::TaskStatus (POS: task status enum)

[OUTPUT]
- TaskFilters: filter set for ``TaskStore.list_tasks``; ``order_by`` is whitelisted at construction

[POS]
Query description layer. Keeps SQL-injectable text (ORDER BY) out of the store: a filter that
constructs is safe to interpolate, anything else raises ValueError.
"""

from datetime import datetime

from .protocols import TaskStatus

_DEFAULT_ORDER_BY = "created_at DESC"
_ALLOWED_ORDER_COLUMNS = {
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
    "priority",
    "status",
    "task_type",
    "user_id",
    "task_id",
}
_ALLOWED_ORDER_DIRECTIONS = {"ASC", "DESC"}


def _sanitize_order_by(order_by: str) -> str:
    """Validate a comma-separated ``column [ASC|DESC]`` list against the column whitelist.

    Raises ValueError for anything else: silently rewriting the sort order hides caller bugs
    (a rewritten multi-term order once turned a priority queue into a LIFO stack).
    """
    terms: list[str] = []
    for raw in order_by.split(","):
        parts = raw.split()
        column = parts[0] if parts else ""
        direction = parts[1].upper() if len(parts) == 2 else "ASC"
        if len(parts) > 2 or column not in _ALLOWED_ORDER_COLUMNS or direction not in _ALLOWED_ORDER_DIRECTIONS:
            raise ValueError(f"Unsupported order_by term: {raw.strip()!r}")
        terms.append(f"{column} {direction}")
    return ", ".join(terms)


class TaskFilters:
    """Filters for querying tasks."""

    def __init__(
        self,
        status: TaskStatus | list[TaskStatus] | None = None,
        task_type: str | list[str] | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        ready_before: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = _DEFAULT_ORDER_BY,
        task_ids: list[str] | None = None,
    ):
        self.status = status
        self.task_type = task_type
        self.user_id = user_id
        self.tags = tags
        self.created_after = created_after
        self.created_before = created_before
        self.ready_before = ready_before
        self.limit = limit
        self.offset = offset
        self.order_by = _sanitize_order_by(order_by)
        self.task_ids = task_ids


__all__ = ["TaskFilters"]
