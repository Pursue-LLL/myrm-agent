"""Batch directory lifecycle helpers — pause/resume/approve-all + shared snapshot.

[INPUT]
- app.database.connection::get_session (POS: 数据库会话)
- app.database.models.batch_directory::BatchDirectoryProjectModel (POS: 批量项目持久化)
- app.database.models.kanban::KanbanTaskModel (POS: 看板任务持久化)
- app.services.batch_directory._helpers (POS: 序列化/查询/状态聚合助手)

[OUTPUT]
- pause_project / resume_project: 批次暂停冻结与恢复
- approve_all_results: 批量接收待审批结果
- _ProjectSettings / _load_project_snapshot / _require_not_paused: 重试与生命周期操作共享的快照助手

[POS]
BatchDirectory 生命周期控制层。负责暂停冻结/恢复解冻、批量接收待审批结果，
以及重试与生命周期操作共享的项目快照加载（`_ProjectSettings`/`_load_project_snapshot`/`_require_not_paused`）。
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
    _latest_tasks_per_directory,
    _reopen_running,
    fetch_project_task_models,
)

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
        stmt = select(KanbanTaskModel).where(KanbanTaskModel.metadata_json["batch_project_id"].as_string() == project_id)
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
            artifact_patterns=(list(model.artifact_patterns_json) if model.artifact_patterns_json else []),
            directories=(list(model.directories_json) if model.directories_json else []),
            status=model.status,
        )
    return settings, tasks


def _require_not_paused(settings: _ProjectSettings, project_id: str) -> None:
    """Reject lifecycle operations while the batch is paused (queue frozen)."""
    if settings.status == "paused":
        raise ValueError(f"Batch project {project_id} is paused; resume it before retrying")


async def pause_project(service: BatchDirectoryService, project_id: str) -> dict[str, object] | None:
    """Pause a running batch: freeze the queued work and stop executing tasks.

    Every non-terminal executable task (READY/BACKLOG/RUNNING) is moved to
    ``BLOCKED(HUMAN, batch_pause)`` so the dispatcher stops picking it up;
    running tasks are cancelled first to stop the agent promptly, and the
    per-pass re-fetch converges any task the dispatcher claimed or a
    concurrent retry created while the queue was being frozen. A task that
    completes while its cancel is in flight keeps its result — it is skipped
    instead of being frozen and re-run after resume. Completed/
    failed/archived results are untouched, and IN_REVIEW results keep waiting
    for approval. The project flips to ``paused`` and can be reopened via
    :func:`resume_project`.
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
                BatchDirectoryProjectModel.status.notin_(list(_PROJECT_TERMINAL_STATUSES)),
            )
            .values(status="paused")
        )
        await session.commit()

    tasks = await fetch_project_task_models(project_id)
    latest = _latest_tasks_per_directory(tasks)
    paused_ids: list[str] = []

    async def _freeze(t: KanbanTaskModel) -> None:
        try:
            # 复查最新状态：cancel 等待期间任务可能已完成/失败落库，
            # 已终态则保留结果跳过冻结，避免恢复后重复执行浪费 token。
            fresh = await service.kanban.get_task(t.id)
            if fresh is None or fresh.status.value not in {
                TaskStatus.READY.value,
                TaskStatus.BACKLOG.value,
                TaskStatus.RUNNING.value,
            }:
                return
            # 先停止 dispatcher 中的 agent 执行，再置 BLOCKED：若任务刚被
            # dispatcher claim，cancel 幂等地中断执行，避免冻结后仍在跑。
            await service.kanban.cancel_task_execution(t.id)
            await service.kanban.move_task(
                t.id,
                TaskStatus.BLOCKED,
                block_kind=BlockKind.HUMAN,
                blocked_reason=_BATCH_PAUSE_BLOCK_REASON,
            )
            paused_ids.append(t.id)
        except Exception as exc:  # noqa: BLE001 - 单任务冻结失败不阻断
            logger.warning("Batch project %s: pause task %s failed: %s", project_id, t.id, exc)

    # 多轮收敛：每轮冻结当前所有可执行任务（READY/BACKLOG/RUNNING），
    # 重新拉取后捕获暂停窗口内 dispatcher 新 claim 或并发重试新创建的任务。
    for _ in range(3):
        to_freeze = [
            t
            for t in latest
            if t.status
            in {
                TaskStatus.READY.value,
                TaskStatus.BACKLOG.value,
                TaskStatus.RUNNING.value,
            }
        ]
        if not to_freeze:
            break
        for t in to_freeze:
            await _freeze(t)
        latest = await fetch_project_task_models(project_id)

    base = await service.get_project(project_id)
    if base is None:
        return None
    base["paused_task_ids"] = paused_ids
    return base


async def resume_project(service: BatchDirectoryService, project_id: str) -> dict[str, object] | None:
    """Resume a paused batch: unblock every task frozen by
    :func:`pause_project` back to READY so the dispatcher schedules them again.

    Only tasks carrying the batch-pause block reason are reopened; unrelated
    BLOCKED tasks (manual or scheduled blocks) are left untouched. The
    project reopens to ``running`` only if it is still ``paused`` — a
    concurrent cancel wins and is never overwritten.
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
            logger.warning("Batch project %s: resume task %s failed: %s", project_id, t.id, exc)

    # 重开条件：至少解冻了一个任务，或已无 batch_pause 冻结任务残留（任务
    # 全部终态，重开后由读取路径自愈收尾）。若解冻全部失败且仍有冻结任务，
    # 保持 paused，避免项目回 running 却无任务可调度而卡死。
    # 重开使用条件更新（仅仍为 paused 才置 running）：并发取消把项目置
    # cancelled 后，恢复不得覆盖取消意图。
    if resumed_ids:
        await _reopen_running(project_id, expected_status="paused")
    else:
        tasks_after = await fetch_project_task_models(project_id)
        still_frozen = any(
            t.status == TaskStatus.BLOCKED.value and t.blocked_reason == _BATCH_PAUSE_BLOCK_REASON
            for t in _latest_tasks_per_directory(tasks_after)
        )
        if not still_frozen:
            await _reopen_running(project_id, expected_status="paused")
    base = await service.get_project(project_id)
    if base is None:
        return None
    base["resumed_task_ids"] = resumed_ids
    return base


async def approve_all_results(service: BatchDirectoryService, project_id: str) -> dict[str, object] | None:
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
            logger.warning("Batch project %s: approve task %s failed: %s", project_id, t.id, exc)

    base = await service.get_project(project_id)
    if base is None:
        return None
    base["approved_task_ids"] = approved_ids
    return base
