"""Batch directory lifecycle helpers — retry/rerun/pause/resume/approve-all.

[INPUT]
- app.database.connection::get_session (POS: 数据库会话)
- app.database.models.batch_directory::BatchDirectoryProjectModel (POS: 批量项目持久化)
- app.database.models.kanban::KanbanTaskModel (POS: 看板任务持久化)
- app.services.batch_directory._helpers (POS: 序列化/查询/路径校验助手)
- app.services.batch_directory._run::fan_out_batch_tasks (POS: 任务扇出助手)

[OUTPUT]
- retry_failed / retry_task / rerun_project: 失败重试与全量重跑
- pause_project / resume_project: 批次暂停冻结与恢复
- approve_all_results: 批量接收待审批结果
- _fan_out / _reopen_running / _next_attempt / _is_retryable_task / _retryable_directories: 内部助手

[POS]
BatchDirectory 生命周期控制层。负责失败目录重发任务、单目录重试、全量重跑、
暂停冻结/恢复队列、批量审批，以及项目状态回置 running。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import BlockKind, TaskStatus
from sqlalchemy import select
from sqlalchemy import update as sa_update

from app.database.connection import get_session
from app.database.models.batch_directory import BatchDirectoryProjectModel
from app.database.models.kanban import KanbanTaskModel
from app.services.batch_directory._helpers import (
    _BATCH_APPROVER,
    _BATCH_PAUSE_BLOCK_REASON,
    _PROJECT_TERMINAL_STATUSES,
    _aggregate_statuses,
    _artifact_status_for_task,
    _latest_tasks_per_directory,
    _task_attempt,
    fetch_project_task_models,
)
from app.services.batch_directory._run import fan_out_batch_tasks

if TYPE_CHECKING:
    from app.services.batch_directory.service import BatchDirectoryService

logger = logging.getLogger(__name__)


@dataclass
class _ProjectSettings:
    """Snapshot of the execution settings a lifecycle operation fans out with."""

    name: str
    prompt: str
    board_id: str | None
    agent_id: str | None
    model_override: str | None
    max_runtime_seconds: int | None
    require_approval: bool
    artifact_patterns: list[str]
    directories: list[str]
    status: str


async def _load_project_snapshot(
    project_id: str,
) -> tuple[_ProjectSettings | None, list[KanbanTaskModel]]:
    """Load project settings and its batch tasks in a single session snapshot.

    Reading both from one session keeps the attempt generation computed by
    ``_fan_out`` consistent with the settings used for the fan-out.
    """
    async with get_session() as session:
        model = await session.get(BatchDirectoryProjectModel, project_id)
        if model is None:
            return None, []
        stmt = select(KanbanTaskModel).where(
            KanbanTaskModel.metadata_json["batch_project_id"].as_string()
            == project_id
        )
        result = await session.execute(stmt)
        tasks = list(result.scalars().all())
        settings = _ProjectSettings(
            name=model.name,
            prompt=model.prompt,
            board_id=model.board_id,
            agent_id=model.agent_id,
            model_override=model.model_override,
            max_runtime_seconds=model.max_runtime_seconds,
            require_approval=model.require_approval,
            artifact_patterns=(
                list(model.artifact_patterns_json)
                if model.artifact_patterns_json
                else []
            ),
            directories=(
                list(model.directories_json) if model.directories_json else []
            ),
            status=model.status,
        )
    return settings, tasks


def _require_not_paused(settings: _ProjectSettings, project_id: str) -> None:
    """Reject lifecycle operations while the batch is paused (queue frozen)."""
    if settings.status == "paused":
        raise ValueError(
            f"Batch project {project_id} is paused; resume it before retrying"
        )


async def retry_failed(
    service: BatchDirectoryService, project_id: str
) -> dict[str, object] | None:
    """Re-run every directory whose current task ended in failed/archived
    state, or completed without producing the required artifacts.

    New Kanban tasks are fanned out for those directories (reusing the
    original board, prompt and execution settings) and the project is
    reopened to ``running``, so terminal detection and the completion
    notification fire again once every task settles. Original task
    records are left untouched for history.
    """
    settings, tasks = await _load_project_snapshot(project_id)
    if settings is None:
        return None
    _require_not_paused(settings, project_id)
    if not settings.board_id:
        raise ValueError("Batch project has no board to schedule retries")

    retry_dirs = _retryable_directories(tasks)
    if not retry_dirs:
        base = await service.get_project(project_id)
        if base is not None:
            base["retried_task_ids"] = []
            base["retry_failed_directories"] = []
        return base

    created, errors = await _fan_out(service, project_id, settings, retry_dirs, tasks)
    await _reopen_running(project_id)
    base = await service.get_project(project_id)
    if base is None:
        return None
    base["retried_task_ids"] = created
    base["retry_failed_directories"] = [d for d, _ in errors]
    return base


async def retry_task(
    service: BatchDirectoryService, project_id: str, task_id: str
) -> dict[str, object] | None:
    """Re-run a single directory by fanning out a fresh task for it.

    Only the current (latest) task of a directory can be retried, and only
    when it ended failed/archived or completed without required artifacts.
    """
    settings, tasks = await _load_project_snapshot(project_id)
    if settings is None:
        return None
    _require_not_paused(settings, project_id)
    if not settings.board_id:
        raise ValueError("Batch project has no board to schedule retries")

    latest = _latest_tasks_per_directory(tasks)
    target = next((t for t in latest if t.id == task_id), None)
    if target is None or not target.workspace_path:
        raise ValueError(
            f"Task {task_id} is not the current task of batch project {project_id}"
        )
    if not _is_retryable_task(target):
        raise ValueError("Only failed or artifact-missing tasks can be retried")

    created, errors = await _fan_out(
        service, project_id, settings, [str(target.workspace_path)], tasks
    )
    await _reopen_running(project_id)
    base = await service.get_project(project_id)
    if base is None:
        return None
    base["retried_task_ids"] = created
    base["retry_failed_directories"] = [d for d, _ in errors]
    return base


async def rerun_project(
    service: BatchDirectoryService, project_id: str
) -> dict[str, object] | None:
    """Re-run every target directory (full rerun): fresh tasks are fanned out
    for all directories and the project reopens to ``running`` regardless of
    prior outcomes.

    Only terminal projects can be rerun — fanning out while tasks are still
    in flight would create duplicate tasks per directory. A paused project is
    also rejected (resume it first).
    """
    settings, tasks = await _load_project_snapshot(project_id)
    if settings is None:
        return None
    if not settings.board_id:
        raise ValueError("Batch project has no board to schedule rerun")
    if not settings.directories:
        raise ValueError("Batch project has no target directories to rerun")
    if settings.status == "paused":
        raise ValueError(
            f"Batch project {project_id} is paused; resume it before rerunning"
        )
    if settings.status not in _PROJECT_TERMINAL_STATUSES:
        raise ValueError(
            "Batch project is still running; wait for it to finish before rerunning"
        )

    created, errors = await _fan_out(
        service, project_id, settings, settings.directories, tasks
    )
    await _reopen_running(project_id)
    base = await service.get_project(project_id)
    if base is None:
        return None
    base["rerun_task_ids"] = created
    base["rerun_failed_directories"] = [d for d, _ in errors]
    return base


async def pause_project(
    service: BatchDirectoryService, project_id: str
) -> dict[str, object] | None:
    """Pause a running batch: freeze the queued work and stop executing tasks.

    Non-terminal tasks are moved to ``BLOCKED(HUMAN, batch_pause)`` so the
    dispatcher stops picking them up; running tasks are cancelled first to
    stop the agent promptly. Completed/failed/archived results are untouched,
    and IN_REVIEW results keep waiting for approval. The project flips to
    ``paused`` and can be reopened via :func:`resume_project`.

    A second convergence pass handles the narrow window where the dispatcher
    re-claims a READY task while the queue is being frozen.
    """
    async with get_session() as session:
        model = await session.get(BatchDirectoryProjectModel, project_id)
        if model is None:
            return None
        if model.status in _PROJECT_TERMINAL_STATUSES:
            raise ValueError("Batch project already finished; nothing to pause")
        if model.status == "paused":
            return await service.get_project(project_id)
        await session.execute(
            sa_update(BatchDirectoryProjectModel)
            .where(
                BatchDirectoryProjectModel.id == project_id,
                BatchDirectoryProjectModel.status.notin_(
                    list(_PROJECT_TERMINAL_STATUSES)
                ),
            )
            .values(status="paused")
        )
        await session.commit()

    tasks = await fetch_project_task_models(project_id)
    latest = _latest_tasks_per_directory(tasks)
    paused_ids: list[str] = []

    async def _freeze(t: KanbanTaskModel) -> None:
        try:
            await service.kanban.move_task(
                t.id,
                TaskStatus.BLOCKED,
                block_kind=BlockKind.HUMAN,
                blocked_reason=_BATCH_PAUSE_BLOCK_REASON,
            )
            paused_ids.append(t.id)
        except Exception as exc:  # noqa: BLE001 - 单任务冻结失败不阻断
            logger.warning(
                "Batch project %s: pause task %s failed: %s", project_id, t.id, exc
            )

    for t in latest:
        status = TaskStatus(t.status) if t.status else None
        if status in (TaskStatus.READY, TaskStatus.BACKLOG):
            await _freeze(t)

    for _ in range(2):  # 双轮收敛：中断运行中任务并消除 dispatcher 重拾窗口
        running = [
            t for t in latest if t.status == TaskStatus.RUNNING.value
        ]
        if not running:
            break
        for t in running:
            await service.kanban.cancel_task_execution(t.id)
            await _freeze(t)
        latest = await fetch_project_task_models(project_id)

    base = await service.get_project(project_id)
    if base is None:
        return None
    base["paused_task_ids"] = paused_ids
    return base


async def resume_project(
    service: BatchDirectoryService, project_id: str
) -> dict[str, object] | None:
    """Resume a paused batch: unblock every task frozen by
    :func:`pause_project` back to READY so the dispatcher schedules them again.

    Only tasks carrying the batch-pause block reason are reopened; unrelated
    BLOCKED tasks (manual or scheduled blocks) are left untouched.
    """
    async with get_session() as session:
        model = await session.get(BatchDirectoryProjectModel, project_id)
        if model is None:
            return None
        if model.status != "paused":
            raise ValueError("Batch project is not paused")

    tasks = await fetch_project_task_models(project_id)
    latest = _latest_tasks_per_directory(tasks)
    resumed_ids: list[str] = []
    for t in latest:
        if t.status != TaskStatus.BLOCKED.value:
            continue
        if t.blocked_reason != _BATCH_PAUSE_BLOCK_REASON:
            continue
        try:
            await service.kanban.move_task(t.id, TaskStatus.READY)
            resumed_ids.append(t.id)
        except Exception as exc:  # noqa: BLE001 - 单任务恢复失败不阻断
            logger.warning(
                "Batch project %s: resume task %s failed: %s", project_id, t.id, exc
            )

    if resumed_ids:
        await _reopen_running(project_id)
    base = await service.get_project(project_id)
    if base is None:
        return None
    base["resumed_task_ids"] = resumed_ids
    return base


async def approve_all_results(
    service: BatchDirectoryService, project_id: str
) -> dict[str, object] | None:
    """Approve every current task awaiting review (IN_REVIEW) at once.

    Reuses the per-task approval gate (idempotent) so results already
    approved or superseded by a retry are untouched; each approved task
    promotes to COMPLETED and triggers terminal detection, which finishes
    the project and fires the completion notification.
    """
    async with get_session() as session:
        model = await session.get(BatchDirectoryProjectModel, project_id)
        if model is None:
            return None

    tasks = await fetch_project_task_models(project_id)
    latest = _latest_tasks_per_directory(tasks)
    approved_ids: list[str] = []
    for t in latest:
        if t.status != TaskStatus.IN_REVIEW.value:
            continue
        try:
            await service.kanban.approve_task(t.id, approver=_BATCH_APPROVER)
            approved_ids.append(t.id)
        except Exception as exc:  # noqa: BLE001 - 单任务审批失败不阻断
            logger.warning(
                "Batch project %s: approve task %s failed: %s", project_id, t.id, exc
            )

    base = await service.get_project(project_id)
    if base is None:
        return None
    base["approved_task_ids"] = approved_ids
    return base


async def _fan_out(
    service: BatchDirectoryService,
    project_id: str,
    settings: _ProjectSettings,
    directories: list[str],
    tasks: list[KanbanTaskModel],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Fan out fresh tasks for ``directories``, stamping the next attempt
    generation so per-directory aggregation can pick the newest task."""
    return await fan_out_batch_tasks(
        service.kanban,
        board_id=settings.board_id,
        project_id=project_id,
        name=settings.name,
        prompt=settings.prompt,
        directories=directories,
        agent_id=settings.agent_id,
        model_override=settings.model_override,
        max_runtime_seconds=settings.max_runtime_seconds,
        require_approval=settings.require_approval,
        artifact_patterns=settings.artifact_patterns,
        attempt=_next_attempt(tasks),
    )


async def _reopen_running(project_id: str) -> None:
    """Reopen a project to ``running`` and refresh aggregation counters.

    Shared by retry/rerun/resume entry points: after tasks are fanned out or
    unblocked, the counters are recomputed from the current task set (one per
    directory) and the finish timestamp is cleared.
    """
    async with get_session() as session:
        model = await session.get(BatchDirectoryProjectModel, project_id)
        if model is None:
            return
        refreshed = await fetch_project_task_models(project_id)
        latest = _latest_tasks_per_directory(refreshed)
        total, completed, failed = _aggregate_statuses(latest)
        model.status = "running"
        model.total_tasks = total
        model.completed_tasks = completed
        model.failed_tasks = failed
        model.finished_at = None
        await session.commit()


def _next_attempt(tasks: list[KanbanTaskModel]) -> int:
    """Next monotonic batch attempt generation for a fan-out.

    Stamped into task metadata so per-directory aggregation can pick the
    newest task even when retries land within the same ``created_at``
    second (see ``_latest_tasks_per_directory``).
    """
    return max((_task_attempt(t) for t in tasks), default=-1) + 1


def _retryable_directories(tasks: list[KanbanTaskModel]) -> list[str]:
    """Workspace paths of directories whose current task can be retried."""
    latest = _latest_tasks_per_directory(tasks)
    return [
        str(t.workspace_path)
        for t in latest
        if t.workspace_path and _is_retryable_task(t)
    ]


def _is_retryable_task(t: KanbanTaskModel) -> bool:
    """A directory can be retried when its current task failed, was
    archived, or completed without producing the required artifacts."""
    if t.status in (TaskStatus.FAILED.value, TaskStatus.ARCHIVED.value):
        return True
    return (
        t.status == TaskStatus.COMPLETED.value
        and _artifact_status_for_task(t) == "missing"
    )
