"""Kanban read/query operations and user comments.

[INPUT]
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)

[OUTPUT]
- get_board, list_boards, get_task, list_tasks, list_task_events, list_task_runs, add_comment

[POS]
Read-only queries and user comment creation for kanban boards and tasks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from myrm_agent_harness.toolkits.kanban.types import (
    KanbanBoard,
    KanbanTask,
    TaskEdge,
    TaskEvent,
    TaskEventKind,
    TaskRun,
    TaskStatus,
)

from app.core.kanban.adapters import SqlAlchemyKanbanStore


async def get_board(store: SqlAlchemyKanbanStore, board_id: str) -> KanbanBoard | None:
    return await store.get_board(board_id)


async def list_boards(store: SqlAlchemyKanbanStore) -> list[KanbanBoard]:
    return await store.list_boards()


async def get_task(store: SqlAlchemyKanbanStore, task_id: str) -> KanbanTask | None:
    return await store.get_task(task_id)


async def list_tasks(
    store: SqlAlchemyKanbanStore,
    board_id: str,
    *,
    status: TaskStatus | None = None,
    agent_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[KanbanTask]:
    return await store.list_tasks(
        board_id, status=status, agent_id=agent_id, limit=limit, offset=offset
    )


async def list_runs(store: SqlAlchemyKanbanStore, task_id: str) -> list[TaskRun]:
    return await store.list_runs(task_id)


async def list_events(
    store: SqlAlchemyKanbanStore,
    task_id: str,
    *,
    since_id: int | None = None,
) -> list[TaskEvent]:
    return await store.list_events(task_id, since_id=since_id)


async def list_board_events(
    store: SqlAlchemyKanbanStore,
    board_id: str,
    *,
    kinds: list[str] | None = None,
    assignee: str | None = None,
    since_id: int | None = None,
    since_time: datetime | None = None,
    limit: int = 50,
) -> list[dict]:
    return await store.list_board_events(
        board_id,
        kinds=kinds,
        assignee=assignee,
        since_id=since_id,
        since_time=since_time,
        limit=limit,
    )


async def list_task_dependencies(store: SqlAlchemyKanbanStore, task_id: str) -> list[str]:
    return await store.list_parents(task_id)


async def list_task_dependents(store: SqlAlchemyKanbanStore, task_id: str) -> list[str]:
    return await store.list_children(task_id)


async def list_board_edges(store: SqlAlchemyKanbanStore, board_id: str) -> list[TaskEdge]:
    return await store.list_board_edges(board_id)


async def clear_agent_references(store: SqlAlchemyKanbanStore, agent_id: str) -> int:
    return await store.clear_agent_references(agent_id)


async def add_comment(
    store: SqlAlchemyKanbanStore,
    task_id: str,
    body: str,
    *,
    author: str = "user",
    publish_event: Callable[[str, str, str], None],
) -> TaskEvent:
    event = await store.append_event(
        task_id,
        TaskEventKind.USER_COMMENT,
        payload={"body": body, "author": author},
    )
    task = await store.get_task(task_id)
    if task:
        publish_event(task.board_id, task_id, "commented")
    return event
