"""Kanban task CRUD operations.

[INPUT]
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- event_publisher (POS: Kanban SSE event publishing helpers.)
- service_types (POS: Kanban service shared types.)

[OUTPUT]
- add_task, update_task, delete_task, bulk_update_tasks

[POS]
Task lifecycle operations: add, update, delete, and bulk update with event publishing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskEventKind, TaskPriority, TaskStatus

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.event_publisher import publish_kanban_event
from app.services.kanban.service_types import UNSET, Sentinel

logger = logging.getLogger(__name__)

ValidateAgentId = Callable[[str], Awaitable[None]]
WakeDispatcher = Callable[[str], None]


async def add_task(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    board_id: str,
    title: str,
    description: str = "",
    priority: TaskPriority = TaskPriority.NORMAL,
    parent_task_id: str | None = None,
    agent_id: str | None = None,
    max_retries: int = 3,
    depends_on: list[str] | None = None,
    extra_skill_ids: list[str] | None = None,
    completion_criteria: str | list[dict[str, str | int]] | None = None,
    initial_status: TaskStatus | None = None,
    max_runtime_seconds: int | None = None,
    workspace_path: str | None = None,
    branch: str | None = None,
    metadata_patch: dict[str, object] | None = None,
    *,
    validate_agent_id: ValidateAgentId,
    wake_dispatcher: WakeDispatcher,
) -> KanbanTask:
    if agent_id is not None:
        await validate_agent_id(agent_id)

    if initial_status is None:
        resolved_status = TaskStatus.BACKLOG if depends_on else TaskStatus.READY
    elif initial_status == TaskStatus.TRIAGE:
        resolved_status = TaskStatus.TRIAGE
    elif initial_status in (TaskStatus.READY, TaskStatus.BACKLOG, TaskStatus.BLOCKED):
        if initial_status == TaskStatus.READY and depends_on:
            resolved_status = TaskStatus.BACKLOG
        else:
            resolved_status = initial_status
    else:
        raise ValueError(f"initial_status must be one of TRIAGE/BACKLOG/READY/BLOCKED, got {initial_status}")

    metadata: dict[str, object] = {}
    if completion_criteria:
        metadata["completion_criteria"] = completion_criteria

    from app.services.agent.goal_registry import get_current_git_branch

    current_branch = await get_current_git_branch()
    if current_branch:
        metadata["branch"] = current_branch
    if metadata_patch:
        metadata.update(metadata_patch)

    task = KanbanTask(
        task_id=uuid.uuid4().hex[:12],
        board_id=board_id,
        title=title,
        description=description,
        status=resolved_status,
        priority=priority,
        agent_id=agent_id,
        parent_task_id=parent_task_id,
        workspace_path=workspace_path,
        branch=branch,
        max_runtime_seconds=max_runtime_seconds,
        extra_skill_ids=extra_skill_ids or [],
        max_retries=max_retries,
        metadata=metadata,
    )
    saved = await store.save_task(task)
    await store.append_event(saved.task_id, TaskEventKind.CREATED)

    if depends_on:
        valid_deps: list[str] = []
        for pid in depends_on:
            parent = await store.get_task(pid)
            if parent is None:
                logger.warning("Skipped dependency %s -> %s (parent not found)", pid, saved.task_id)
                continue
            valid_deps.append(pid)
        for pid in valid_deps:
            try:
                await store.add_edge(pid, saved.task_id)
            except ValueError:
                logger.warning(
                    "Skipped dependency %s -> %s (cycle detected)",
                    pid,
                    saved.task_id,
                )
        if not valid_deps and depends_on:
            saved.status = TaskStatus.READY
            saved = await store.save_task(saved)

    if board_id in dispatchers:
        wake_dispatcher(board_id)
    publish_kanban_event(board_id, saved.task_id, "created", title=saved.title)
    return saved


async def update_task(
    store: SqlAlchemyKanbanStore,
    task_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    priority: TaskPriority | None = None,
    agent_id: str | None | Sentinel = UNSET,
    extra_skill_ids: list[str] | None | Sentinel = UNSET,
    max_runtime_seconds: int | None | Sentinel = UNSET,
    completion_criteria: str | list[dict[str, str | int]] | None = None,
    result: str | None = None,
    metadata: dict[str, object] | None = None,
    validate_agent_id: ValidateAgentId,
) -> KanbanTask | None:
    task = await store.get_task(task_id)
    if task is None:
        return None
    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if priority is not None:
        task.priority = priority
    old_agent_id: str | None = task.agent_id
    agent_changed = False
    if not isinstance(agent_id, Sentinel):
        if agent_id is not None and agent_id != task.agent_id:
            await validate_agent_id(agent_id)
        if agent_id != task.agent_id:
            agent_changed = True
            task.consecutive_failures = 0
            task.error = ""
        task.agent_id = agent_id
    if not isinstance(extra_skill_ids, Sentinel):
        task.extra_skill_ids = extra_skill_ids or []
    if not isinstance(max_runtime_seconds, Sentinel):
        task.max_runtime_seconds = max_runtime_seconds
    if completion_criteria is not None:
        if completion_criteria:
            task.metadata["completion_criteria"] = completion_criteria
        else:
            task.metadata.pop("completion_criteria", None)
    edited_fields: list[str] = []
    if result is not None:
        task.result = result
        edited_fields.append("result")
    if metadata is not None:
        task.metadata.update(metadata)
        edited_fields.append("metadata")
    saved = await store.save_task(task)
    publish_kanban_event(saved.board_id, task_id, "updated", title=saved.title)
    if agent_changed:
        await store.append_event(
            task_id,
            TaskEventKind.ASSIGNED,
            payload={
                "old_agent_id": old_agent_id,
                "new_agent_id": saved.agent_id,
            },
        )
    if edited_fields:
        await store.append_event(
            task_id,
            TaskEventKind.EDITED,
            payload={"fields": edited_fields},
        )
    return saved


async def delete_task(store: SqlAlchemyKanbanStore, task_id: str) -> bool:
    task = await store.get_task(task_id)
    board_id = task.board_id if task else ""
    children_ids = await store.list_children(task_id)
    deleted = await store.delete_task(task_id)
    if deleted and children_ids:
        for child_id in children_ids:
            child = await store.get_task(child_id)
            if child is None or child.status != TaskStatus.BACKLOG:
                continue
            if await store.are_dependencies_met(child_id):
                child.status = TaskStatus.READY
                await store.save_task(child)
                await store.append_event(
                    child_id,
                    TaskEventKind.PROMOTED,
                    payload={"reason": "parent_deleted", "deleted_task_id": task_id},
                )
                publish_kanban_event(child.board_id, child_id, "promoted")
    if deleted and board_id:
        publish_kanban_event(board_id, task_id, "deleted")
    return deleted
