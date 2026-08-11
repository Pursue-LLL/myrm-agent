"""Batch directory read/aggregation helpers.

[INPUT]
- app.database.connection::get_session (POS: 数据库会话)
- app.database.models.batch_directory::BatchDirectoryProjectModel (POS: 批量项目持久化)
- app.database.models.kanban::KanbanTaskModel (POS: 看板任务持久化)
- app.services.batch_directory._helpers (POS: 序列化/查询/路径校验助手)

[OUTPUT]
- list_projects / get_project: 项目列表/详情聚合（latest-per-directory）
- _resolve_artifact_results: 任务产物校验聚合
- _schedule_finalize_if_due: 读取路径终态自愈调度

[POS]
BatchDirectory 只读聚合层。不承载写编排，仅做进度聚合、产物校验与终态自愈调度。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from app.database.connection import get_session
from app.database.models.batch_directory import BatchDirectoryProjectModel
from app.database.models.kanban import KanbanTaskModel
from app.services.batch_directory._helpers import (
    _PROJECT_TERMINAL_STATUSES,
    _aggregate_statuses,
    _artifact_status_for_task,
    _failed_directory_paths,
    _latest_tasks_per_directory,
    _project_to_dict,
    fetch_project_task_models,
)

if TYPE_CHECKING:
    from app.services.batch_directory.service import BatchDirectoryService

logger = logging.getLogger(__name__)


async def list_projects(service: BatchDirectoryService) -> list[dict[str, object]]:
    async with get_session() as session:
        stmt = select(BatchDirectoryProjectModel).order_by(
            BatchDirectoryProjectModel.created_at.desc()
        )
        result = await session.execute(stmt)
        projects = list(result.scalars().all())

    if not projects:
        return []

    # 批量刷新聚合统计（避免 N+1）
    ids = [p.id for p in projects]
    rows: dict[str, list[KanbanTaskModel]] = {}
    async with get_session() as session:
        stmt = select(KanbanTaskModel).where(
            or_(
                *[
                    KanbanTaskModel.metadata_json["batch_project_id"].as_string()
                    == pid
                    for pid in ids
                ]
            )
        )
        result = await session.execute(stmt)
        for task in result.scalars().all():
            meta = task.metadata_json or {}
            pid = meta.get("batch_project_id")
            if pid:
                rows.setdefault(str(pid), []).append(task)

    items: list[dict[str, object]] = []
    for p in projects:
        d = _project_to_dict(p)
        tasks = rows.get(p.id, [])
        latest = _latest_tasks_per_directory(tasks)
        total, completed, failed = _aggregate_statuses(latest)
        total = total if total else p.total_tasks
        d["total_tasks"] = total
        d["completed_tasks"] = completed
        d["failed_tasks"] = failed
        d["failed_directories"] = _failed_directory_paths(latest)
        _schedule_finalize_if_due(
            service,
            p.id,
            status=str(d["status"]),
            total=total,
            done=completed + failed,
        )
        items.append(d)
    return items


async def get_project(
    service: BatchDirectoryService, project_id: str
) -> dict[str, object] | None:
    async with get_session() as session:
        model = await session.get(BatchDirectoryProjectModel, project_id)
        if model is None:
            return None
        base = _project_to_dict(model)

    tasks = await fetch_project_task_models(project_id)
    latest = _latest_tasks_per_directory(tasks)
    total, completed, failed = _aggregate_statuses(latest)
    total = total if total else model.total_tasks
    base["total_tasks"] = total
    base["completed_tasks"] = completed
    base["failed_tasks"] = failed
    base["failed_directories"] = _failed_directory_paths(latest)
    task_items, missing_artifacts = await _resolve_artifact_results(latest)
    base["tasks"] = task_items
    base["missing_artifact_directories"] = missing_artifacts
    _schedule_finalize_if_due(
        service,
        project_id,
        status=str(base["status"]),
        total=total,
        done=completed + failed,
    )
    return base


async def _resolve_artifact_results(
    tasks: list[KanbanTaskModel],
) -> tuple[list[dict[str, object]], list[str]]:
    """Build task payloads with per-task artifact status and collect the
    list of workspace directories missing required output artifacts.

    Artifact glob verification touches the filesystem, so it runs in a
    worker thread to avoid blocking the event loop.
    """

    def _sync() -> tuple[list[dict[str, object]], list[str]]:
        items: list[dict[str, object]] = []
        missing: list[str] = []
        for t in tasks:
            artifact_status = _artifact_status_for_task(t)
            if artifact_status == "missing" and t.workspace_path:
                missing.append(str(t.workspace_path))
            items.append(
                {
                    "task_id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "workspace_path": t.workspace_path,
                    "agent_id": t.agent_id,
                    "result": t.result,
                    "error": t.error,
                    "created_at": (
                        t.created_at.isoformat() if t.created_at else None
                    ),
                    "completed_at": (
                        t.completed_at.isoformat() if t.completed_at else None
                    ),
                    "artifact_status": artifact_status,
                }
            )
        return items, missing

    return await asyncio.to_thread(_sync)


def _schedule_finalize_if_due(
    service: BatchDirectoryService,
    project_id: str,
    *,
    status: str,
    total: int,
    done: int,
) -> None:
    """Self-heal the case where the last task reached a terminal state
    without a dispatcher event (e.g. REST manual move to a terminal
    status) — schedule the (idempotent) finalize check."""
    if status in _PROJECT_TERMINAL_STATUSES or not total or done < total:
        return
    try:
        asyncio.get_running_loop().create_task(service.maybe_finalize(project_id))
    except RuntimeError:  # pragma: no cover - 无事件循环时不调度
        logger.debug("No running loop; skip batch finalize for %s", project_id)
