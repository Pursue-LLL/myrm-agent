"""Kanban task move, reclaim, and execution cancel orchestration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner
from myrm_agent_harness.toolkits.kanban.types import (
    _TRIAGE_ALLOWED_TARGETS,
    BlockKind,
    KanbanTask,
    TaskEventKind,
    TaskRunOutcome,
    TaskStatus,
)

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.dependency_ops import promote_dependents
from app.services.kanban.event_publisher import publish_kanban_event
from app.services.kanban.service_types import (
    STATUS_TO_EVENT_KIND,
    SYNTHETIC_RUN_TARGETS,
    TARGET_TO_RUN_OUTCOME,
    DependencyUnmetError,
    UnmetParentInfo,
)

logger = logging.getLogger(__name__)

ValidateAgentId = Callable[[str], Awaitable[None]]
CleanupWorktree = Callable[[KanbanTask], Awaitable[None]]
WakeDispatcher = Callable[[str], None]


async def synthesize_run(
    store: SqlAlchemyKanbanStore,
    task_id: str,
    target_status: TaskStatus,
    *,
    result: str = "",
    error: str = "",
) -> str:
    """Create a zero-duration synthetic TaskRun for unclaimed terminal transitions."""
    run = await store.create_run(task_id, worker_id="manual")
    outcome = TARGET_TO_RUN_OUTCOME[target_status]
    await store.complete_run(
        run.run_id,
        outcome,
        summary=result,
        error=error,
    )
    return run.run_id


async def cleanup_task_worktree(
    runner: TaskRunner | None,
    task: KanbanTask,
) -> None:
    """Delegate worktree cleanup to the runner if it supports it."""
    if runner is not None and hasattr(runner, "cleanup_worktree"):
        try:
            await runner.cleanup_worktree(task)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning(
                "Worktree cleanup failed for task %s: %s",
                task.task_id[:8],
                exc,
            )


async def move_task(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    runner: TaskRunner | None,
    task_id: str,
    target_status: TaskStatus,
    *,
    force: bool = False,
    block_kind: BlockKind | None = None,
    blocked_reason: str | None = None,
    scheduled_until: datetime | None = None,
    result: str | None = None,
    metadata: dict[str, object] | None = None,
    wake_dispatcher: WakeDispatcher,
) -> KanbanTask | None:
    task = await store.get_task(task_id)
    if task is None:
        return None
    if task.is_terminal and target_status != TaskStatus.ARCHIVED:
        raise ValueError(f"Cannot move terminal task (status={task.status}) to {target_status}")
    if task.status == TaskStatus.TRIAGE and target_status not in _TRIAGE_ALLOWED_TARGETS:
        raise ValueError(f"TRIAGE task can only move to BACKLOG/READY/ARCHIVED, got {target_status}")
    old_status = task.status
    task.status = target_status
    unsatisfied_deps: list[str] = []
    if target_status == TaskStatus.BLOCKED:
        task.block_kind = block_kind or BlockKind.HUMAN
        task.scheduled_until = scheduled_until
        if blocked_reason:
            task.blocked_reason = blocked_reason
    if target_status == TaskStatus.READY:
        task.blocked_reason = None
        task.block_kind = None
        task.scheduled_until = None
        if old_status == TaskStatus.BLOCKED:
            task.consecutive_failures = 0
            task.error = ""
        if not await store.are_dependencies_met(task_id):
            if force:
                unsatisfied_deps = await store.list_parents(task_id)
            else:
                parent_ids = await store.list_parents(task_id)
                details: list[UnmetParentInfo] = []
                for pid in parent_ids:
                    parent = await store.get_task(pid)
                    if parent and not parent.is_terminal:
                        details.append(
                            UnmetParentInfo(
                                task_id=pid,
                                title=parent.title,
                                status=parent.status.value,
                            )
                        )
                raise DependencyUnmetError(
                    task_id,
                    [d["task_id"] for d in details],
                    unmet_details=details,
                )
    if result is not None:
        task.result = result
    if metadata is not None:
        if task.metadata is None:
            task.metadata = {}
        task.metadata["handoff"] = metadata
    if target_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED):
        task.completed_at = datetime.now(UTC)
    if old_status == TaskStatus.RUNNING and not task.is_terminal:
        task.last_heartbeat_at = None
        task.progress_note = None
    saved = await store.save_task(task)

    synthetic_run_id: str | None = None

    if old_status == TaskStatus.RUNNING and not saved.is_terminal:
        await store.append_event(
            task_id,
            TaskEventKind.RECLAIMED,
            payload={"from": old_status.value, "to": target_status.value},
        )
        runs = await store.list_runs(task_id)
        for run in reversed(runs):
            if not run.is_finished:
                await store.complete_run(
                    run.run_id,
                    TaskRunOutcome.RECLAIMED,
                    error="Manual reclaim via move_task",
                )
                break

    needs_synthetic = old_status != TaskStatus.RUNNING and target_status in SYNTHETIC_RUN_TARGETS
    if needs_synthetic:
        synthetic_run_id = await synthesize_run(
            store,
            task_id,
            target_status,
            result=result or "",
            error=blocked_reason or "",
        )

    event_kind = STATUS_TO_EVENT_KIND.get(saved.status)
    if old_status == TaskStatus.BLOCKED and saved.status == TaskStatus.READY:
        event_kind = TaskEventKind.UNBLOCKED
    if old_status == TaskStatus.RUNNING and not saved.is_terminal:
        event_kind = None
    if event_kind:
        event_payload: dict[str, object] = {
            "from": old_status.value,
            "to": target_status.value,
        }
        if saved.block_kind:
            event_payload["block_kind"] = saved.block_kind.value
        if old_status == TaskStatus.BLOCKED and saved.status == TaskStatus.READY:
            event_payload["source"] = "manual"
        await store.append_event(
            task_id,
            event_kind,
            payload=event_payload,
            run_id=synthetic_run_id,
        )
    if unsatisfied_deps:
        await store.append_event(
            task_id,
            TaskEventKind.PROMOTED,
            payload={
                "forced": True,
                "unsatisfied_deps": unsatisfied_deps,
                "from": old_status.value,
            },
        )

    if target_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED):
        await promote_dependents(store, task_id)

    if target_status == TaskStatus.ARCHIVED and saved.branch:
        await cleanup_task_worktree(runner, saved)

    if task.board_id in dispatchers:
        wake_dispatcher(task.board_id)
    publish_kanban_event(
        saved.board_id,
        task_id,
        "moved",
        title=saved.title,
        detail=saved.result or saved.blocked_reason or saved.error or "",
        status=saved.status.value,
    )
    return saved


async def cancel_task_execution(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    task_id: str,
) -> bool:
    """Cancel asyncio execution without modifying task state."""
    task = await store.get_task(task_id)
    if task is None:
        return False
    dispatcher = dispatchers.get(task.board_id)
    if dispatcher:
        return await dispatcher.cancel_execution(task_id)
    return False


async def reclaim_task(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    task_id: str,
    *,
    reason: str | None = None,
    new_agent_id: str | None = None,
    validate_agent_id: ValidateAgentId,
) -> KanbanTask | None:
    """Manually reclaim a RUNNING task and optionally reassign agent."""
    task = await store.get_task(task_id)
    if task is None:
        return None
    if task.status != TaskStatus.RUNNING:
        raise ValueError(
            f"Cannot reclaim task in status '{task.status.value}'; only RUNNING tasks can be reclaimed"
        )

    dispatcher = dispatchers.get(task.board_id)
    if dispatcher:
        await dispatcher.reclaim_task(task_id, reason)
    else:
        task.status = TaskStatus.READY
        task.consecutive_failures = 0
        task.error = ""
        task.last_heartbeat_at = None
        task.progress_note = None
        await store.save_task(task)
        await store.append_event(
            task_id,
            TaskEventKind.RECLAIMED,
            payload={"manual": True, "reason": reason or "user request"},
        )

    if new_agent_id is not None:
        if new_agent_id:
            await validate_agent_id(new_agent_id)
        task = await store.get_task(task_id)
        if task is not None:
            old_agent_id = task.agent_id
            task.agent_id = new_agent_id or None
            await store.save_task(task)
            await store.append_event(
                task_id,
                TaskEventKind.ASSIGNED,
                payload={
                    "old_agent_id": old_agent_id,
                    "new_agent_id": task.agent_id,
                },
            )

    task = await store.get_task(task_id)
    if task:
        publish_kanban_event(
            task.board_id,
            task_id,
            "reclaimed",
            title=task.title,
            detail=reason or "user request",
        )
    return task
