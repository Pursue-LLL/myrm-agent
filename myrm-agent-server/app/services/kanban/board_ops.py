"""Kanban board CRUD operations."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner
from myrm_agent_harness.toolkits.kanban.types import BoardSettings, KanbanBoard

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.event_publisher import publish_kanban_event

StartDispatcher = Callable[[str, TaskRunner], Awaitable[object]]


async def create_board(
    store: SqlAlchemyKanbanStore,
    name: str,
    description: str = "",
    settings: BoardSettings | None = None,
    *,
    runner: TaskRunner | None = None,
    start_dispatcher: StartDispatcher | None = None,
) -> KanbanBoard:
    board = KanbanBoard(
        board_id=uuid.uuid4().hex[:12],
        name=name,
        description=description,
        settings=settings or BoardSettings(),
    )
    saved = await store.save_board(board)
    if runner is not None and start_dispatcher is not None:
        await start_dispatcher(saved.board_id, runner)
    return saved


async def update_active_tasks_branch_metadata(
    store: SqlAlchemyKanbanStore,
    new_branch: str,
    old_branch: str | None = None,
    migrated: bool = False,
    board_id: str | None = None,
) -> int:
    updated_tasks = await store.update_active_tasks_branch_metadata(
        new_branch, old_branch, migrated, board_id
    )
    for task in updated_tasks:
        publish_kanban_event(task.board_id, task.task_id, "updated", title=task.title)
    return len(updated_tasks)


async def update_board(
    store: SqlAlchemyKanbanStore,
    board_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    settings: BoardSettings | None = None,
) -> KanbanBoard | None:
    board = await store.get_board(board_id)
    if board is None:
        return None
    if name is not None:
        board.name = name
    if description is not None:
        board.description = description
    if settings is not None:
        board.settings = settings
    return await store.save_board(board)


async def delete_board(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    board_id: str,
) -> bool:
    if board_id in dispatchers:
        await dispatchers[board_id].stop()
        del dispatchers[board_id]
    return await store.delete_board(board_id)
