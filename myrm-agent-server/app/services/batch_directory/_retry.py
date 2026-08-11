"""Batch directory retry/rerun lifecycle helpers.

[INPUT]
- app.database.models.kanban::KanbanTaskModel (POS: 看板任务持久化)
- app.services.batch_directory._helpers (POS: 序列化/查询/状态聚合助手)
- app.services.batch_directory._run::fan_out_batch_tasks (POS: 任务扇出助手)
- app.services.batch_directory._lifecycle::_load_project_snapshot / _require_not_paused (POS: 共享快照)

[OUTPUT]
- retry_failed / retry_task / rerun_project: 失败重试与全量重跑
- _fan_out / _next_attempt / _is_retryable_task / _retryable_directories: 内部助手

[POS]
BatchDirectory 重试/重跑层。负责失败目录重发任务、单目录重试、全量重跑，
以及项目状态回置 running。暂停/恢复/审批见 `_lifecycle.py`。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.database.models.kanban import KanbanTaskModel
from app.services.batch_directory._helpers import (
    _PROJECT_TERMINAL_STATUSES,
    _artifact_status_for_task,
    _latest_tasks_per_directory,
    _reopen_running,
    _task_attempt,
)
from app.services.batch_directory._lifecycle import (
    _load_project_snapshot,
    _ProjectSettings,
    _require_not_paused,
)
from app.services.batch_directory._run import fan_out_batch_tasks

if TYPE_CHECKING:
    from app.services.batch_directory.service import BatchDirectoryService


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
