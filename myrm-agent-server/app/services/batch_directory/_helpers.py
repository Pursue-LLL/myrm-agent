"""Batch directory serialization + query helpers.

[INPUT]
- app.database.models.batch_directory::BatchDirectoryProjectModel (POS: 批量项目持久化)
- myrm_agent_harness.agent.security.path_security::is_dangerous_path (POS: 路径安全校验)

[OUTPUT]
- fetch_project_task_models: 按 batch_project_id 查询任务（服务内复用）
- _project_to_dict / _aggregate_statuses / _resolve_directory: 序列化与校验助手

[POS]
纯助手函数（无业务编排），从 service.py 拆出以维持 400 行预算；
公共 API 仍由 service.py 转发，模块间无环形依赖。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from myrm_agent_harness.toolkits.kanban.types import TaskStatus
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models.batch_directory import BatchDirectoryProjectModel
from app.database.models.kanban import KanbanTaskModel

# 任务终态：completed/failed/archived 视为不再由 dispatcher 调度
_TERMINAL_STATUSES = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED}
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _project_to_dict(p: BatchDirectoryProjectModel) -> dict[str, object]:
    return {
        "project_id": p.id,
        "name": p.name,
        "prompt": p.prompt,
        "board_id": p.board_id,
        "status": p.status,
        "concurrency": p.concurrency,
        "agent_id": p.agent_id,
        "model_override": p.model_override,
        "max_runtime_seconds": p.max_runtime_seconds,
        "require_approval": p.require_approval,
        "notify_enabled": p.notify_enabled,
        "directories": list(p.directories_json) if p.directories_json else [],
        "artifact_patterns": list(p.artifact_patterns_json) if p.artifact_patterns_json else [],
        "total_tasks": p.total_tasks,
        "completed_tasks": p.completed_tasks,
        "failed_tasks": p.failed_tasks,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "started_at": p.started_at.isoformat() if p.started_at else None,
        "finished_at": p.finished_at.isoformat() if p.finished_at else None,
    }


def _is_dangerous(path: Path) -> bool:
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    try:
        return is_dangerous_path(str(path))
    except Exception:  # pragma: no cover - 安全函数失败时保守拒绝
        return True


def _resolve_directory(path: str) -> Path:
    """Resolve and validate a target directory path."""
    resolved = Path(path).expanduser().resolve()
    if _is_dangerous(resolved):
        raise ValueError(f"Access denied for path: {path}")
    if not resolved.is_dir():
        raise ValueError(f"Directory does not exist: {path}")
    return resolved


async def fetch_project_task_models(project_id: str) -> list[KanbanTaskModel]:
    """Load Kanban tasks linked to a batch project via metadata `batch_project_id`."""
    async with get_session() as session:
        stmt = select(KanbanTaskModel).where(
            KanbanTaskModel.metadata_json["batch_project_id"].as_string() == project_id
        ).order_by(KanbanTaskModel.created_at)
        result = await session.execute(stmt)
        return list(result.scalars().all())


def _aggregate_statuses(tasks: list[KanbanTaskModel]) -> tuple[int, int, int]:
    """Return (total, completed, failed) counts from the given tasks."""
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED.value)
    failed = sum(1 for t in tasks if t.status in (TaskStatus.FAILED.value, TaskStatus.ARCHIVED.value))
    return total, completed, failed
