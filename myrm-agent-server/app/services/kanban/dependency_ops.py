"""Kanban dependency edges and manual promote operations."""

from __future__ import annotations

import logging
from collections.abc import Callable

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.types import TaskEdge, TaskEventKind, TaskStatus

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.event_publisher import publish_kanban_event
from app.services.kanban.service_types import PromoteResult, UnmetParentInfo

logger = logging.getLogger(__name__)

WakeDispatcher = Callable[[str], None]


async def promote_dependents(
    store: SqlAlchemyKanbanStore,
    completed_task_id: str,
) -> None:
    """Promote BACKLOG children to READY when all dependencies are met."""
    children_ids = await store.list_children(completed_task_id)
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
                payload={"trigger_task_id": completed_task_id},
            )
            publish_kanban_event(child.board_id, child_id, "promoted")
            logger.info(
                "Task %s promoted to READY (parent %s completed)",
                child_id,
                completed_task_id,
            )


async def promote_task(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    task_id: str,
    *,
    force: bool = False,
    reason: str | None = None,
    wake_dispatcher: WakeDispatcher,
) -> PromoteResult:
    """Manually promote a BACKLOG task to READY."""
    task = await store.get_task(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")
    if task.status != TaskStatus.BACKLOG:
        raise ValueError(f"Only BACKLOG tasks can be promoted, got {task.status.value}")

    parent_ids = await store.list_parents(task_id)
    unmet: list[UnmetParentInfo] = []
    for pid in parent_ids:
        parent = await store.get_task(pid)
        if parent and not parent.is_terminal:
            unmet.append(
                UnmetParentInfo(
                    task_id=pid,
                    title=parent.title,
                    status=parent.status.value,
                )
            )

    if unmet and not force:
        return PromoteResult(promoted=False, forced=False, unmet_parents=unmet)

    task.status = TaskStatus.READY
    task.blocked_reason = None
    await store.save_task(task)
    await store.append_event(
        task_id,
        TaskEventKind.PROMOTED,
        payload={
            "forced": bool(unmet),
            "reason": reason or "",
            "skipped_parents": [p["task_id"] for p in unmet],
        },
    )
    publish_kanban_event(task.board_id, task_id, "promoted", title=task.title)
    if task.board_id in dispatchers:
        wake_dispatcher(task.board_id)
    logger.info(
        "Task %s manually promoted to READY (force=%s, skipped=%d parents)",
        task_id,
        bool(unmet),
        len(unmet),
    )
    return PromoteResult(
        promoted=True,
        forced=bool(unmet),
        reason=reason,
        unmet_parents=unmet,
    )


async def add_dependency(
    store: SqlAlchemyKanbanStore,
    child_task_id: str,
    parent_task_id: str,
) -> TaskEdge:
    edge = await store.add_edge(parent_task_id, child_task_id)
    child = await store.get_task(child_task_id)
    if child and child.status == TaskStatus.READY:
        deps_met = await store.are_dependencies_met(child_task_id)
        if not deps_met:
            child.status = TaskStatus.BACKLOG
            await store.save_task(child)
    if child:
        publish_kanban_event(child.board_id, child_task_id, "dependency_added")
    return edge


async def remove_dependency(
    store: SqlAlchemyKanbanStore,
    child_task_id: str,
    parent_task_id: str,
) -> bool:
    removed = await store.remove_edge(parent_task_id, child_task_id)
    if removed:
        child = await store.get_task(child_task_id)
        if child and child.status == TaskStatus.BACKLOG:
            if await store.are_dependencies_met(child_task_id):
                child.status = TaskStatus.READY
                await store.save_task(child)
                await store.append_event(
                    child_task_id,
                    TaskEventKind.PROMOTED,
                    payload={"reason": "dependency_removed"},
                )
        if child:
            publish_kanban_event(child.board_id, child_task_id, "dependency_removed")
    return removed
