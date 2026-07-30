"""Kanban board CRUD operations.

[INPUT]
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- event_publisher (POS: Kanban SSE event publishing helpers.)

[OUTPUT]
- create_board, delete_board, update_board, update_active_tasks_branch_metadata

[POS]
Kanban board lifecycle operations: create, delete, update, and branch metadata sync.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner
from myrm_agent_harness.toolkits.kanban.types import BoardSettings, KanbanBoard
from sqlalchemy import select

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.database.connection import get_session
from app.database.models.milestone import Milestone
from app.database.models.project import Project
from app.services.kanban.event_publisher import publish_kanban_event

StartDispatcher = Callable[[str, TaskRunner], Awaitable[object]]


def _normalize_optional_scope(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


async def _resolve_board_scope(
    *,
    project_id: str | None,
    milestone_id: str | None,
) -> tuple[str | None, str | None]:
    resolved_project_id = _normalize_optional_scope(project_id)
    resolved_milestone_id = _normalize_optional_scope(milestone_id)
    async with get_session() as db:
        if resolved_milestone_id is not None:
            milestone_stmt = select(Milestone).where(Milestone.id == resolved_milestone_id)
            milestone = (await db.execute(milestone_stmt)).scalar_one_or_none()
            if milestone is None:
                raise ValueError(f"Milestone {resolved_milestone_id} not found")
            if resolved_project_id is not None and milestone.project_id != resolved_project_id:
                raise ValueError(
                    f"Milestone {resolved_milestone_id} does not belong to project {resolved_project_id}"
                )
            resolved_project_id = milestone.project_id

        if resolved_project_id is not None:
            project_stmt = select(Project).where(Project.id == resolved_project_id)
            project = (await db.execute(project_stmt)).scalar_one_or_none()
            if project is None:
                raise ValueError(f"Project {resolved_project_id} not found")

    return resolved_project_id, resolved_milestone_id


async def create_board(
    store: SqlAlchemyKanbanStore,
    name: str,
    description: str = "",
    settings: BoardSettings | None = None,
    *,
    project_id: str | None = None,
    milestone_id: str | None = None,
    runner: TaskRunner | None = None,
    start_dispatcher: StartDispatcher | None = None,
) -> KanbanBoard:
    resolved_project_id, resolved_milestone_id = await _resolve_board_scope(
        project_id=project_id,
        milestone_id=milestone_id,
    )
    board = KanbanBoard(
        board_id=uuid.uuid4().hex[:12],
        name=name,
        description=description,
        settings=settings or BoardSettings(),
    )
    saved = await store.save_board(board)
    if resolved_project_id is not None or resolved_milestone_id is not None:
        try:
            await store.set_board_scope(
                saved.board_id,
                project_id=resolved_project_id,
                milestone_id=resolved_milestone_id,
            )
        except Exception:
            await store.delete_board(saved.board_id)
            raise
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
