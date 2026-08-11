"""Batch directory serialization + query helpers.

[INPUT]
- app.database.models.batch_directory::BatchDirectoryProjectModel (POS: 批量项目持久化)
- myrm_agent_harness.agent.security.path_security::is_dangerous_path (POS: 路径安全校验)

[OUTPUT]
- fetch_project_task_models: 按 batch_project_id 查询任务（服务内复用）
- _latest_tasks_per_directory: 每目录取最新任务（重试后聚合口径）
- _project_to_dict / _aggregate_statuses / _resolve_directory: 序列化与校验助手
- _send_completion_notification: 批次终态系统通知（携带 action_url 深链）
- _PROJECT_TERMINAL_STATUSES / _BATCH_PAUSE_BLOCK_REASON / _BATCH_APPROVER: 批次终态与暂停/审批标记常量

[POS]
纯助手函数（无业务编排）。`_validate_artifact_patterns` 同时被 API schemas
直接引用做创建期校验，模块间无环形依赖。
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
# 批量项目终态：到达后不再接受调度、可安全删除
_PROJECT_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
# 批次暂停冻结标记（写入任务的 blocked_reason，恢复时据此筛选）
_BATCH_PAUSE_BLOCK_REASON = "batch_pause"
_BATCH_APPROVER = "batch:approve-all"


def _failed_directory_paths(tasks: list[KanbanTaskModel]) -> list[str]:
    """Return workspace paths of tasks that did not complete (failed/archived)."""
    return [
        str(t.workspace_path)
        for t in tasks
        if t.workspace_path
        and t.status in (TaskStatus.FAILED.value, TaskStatus.ARCHIVED.value)
    ]


def _task_attempt(t: KanbanTaskModel) -> int:
    """Monotonic batch attempt counter stamped by the fan-out (0 = initial)."""
    return int((t.metadata_json or {}).get("batch_attempt", 0) or 0)


def _latest_tasks_per_directory(
    tasks: list[KanbanTaskModel],
) -> list[KanbanTaskModel]:
    """Return the most recent task record per target directory.

    Retried directories carry multiple task records; only the latest one
    reflects the current attempt, so aggregation and terminal detection must
    key on it. ``batch_attempt`` is the authoritative sort key — it strictly
    increases per retry/rerun while ``created_at`` only has second precision
    (a retry issued within the same second would otherwise be indistinguishable
    from the original run). Tasks without a workspace path (not produced by
    the batch fan-out) are kept as-is, keyed by their own id.
    """
    latest: dict[str, KanbanTaskModel] = {}
    for t in tasks:
        key = str(t.workspace_path) if t.workspace_path else t.id
        prev = latest.get(key)
        if prev is None or _is_later_task(t, prev):
            latest[key] = t
    return list(latest.values())


def _is_later_task(new: KanbanTaskModel, prev: KanbanTaskModel) -> bool:
    attempt_new, attempt_prev = _task_attempt(new), _task_attempt(prev)
    if attempt_new != attempt_prev:
        return attempt_new > attempt_prev
    created_new = new.created_at or datetime.min.replace(tzinfo=timezone.utc)
    created_prev = prev.created_at or datetime.min.replace(tzinfo=timezone.utc)
    return created_new > created_prev


def _artifact_status_for_task(t: KanbanTaskModel) -> str:
    """Per-task artifact verification result: verified / missing / not_specified.

    Only completed tasks with declared ``artifact_patterns`` are checked;
    everything else reports ``not_specified``.
    """
    if t.status != TaskStatus.COMPLETED.value or not t.workspace_path:
        return "not_specified"
    patterns = list((t.metadata_json or {}).get("artifact_patterns") or [])
    if not patterns:
        return "not_specified"
    return (
        "verified"
        if _verify_artifact_patterns(t.workspace_path, patterns)
        else "missing"
    )


def _validate_artifact_patterns(patterns: list[str] | None) -> list[str]:
    """Validate artifact glob patterns: relative, non-empty, no traversal.

    Returns the stripped pattern list. Raises ``ValueError`` with a concrete
    reason for the first offending pattern. Applied at creation time so a
    malformed pattern can never reach the runtime glob walk.
    """
    if not patterns:
        return []
    cleaned: list[str] = []
    for raw in patterns:
        pattern = raw.strip()
        if not pattern:
            raise ValueError("Artifact patterns must not be empty")
        if Path(pattern).is_absolute():
            raise ValueError(f"Artifact pattern must be relative: {pattern}")
        if any(part == ".." for part in Path(pattern).parts):
            raise ValueError(
                f"Artifact pattern must stay inside the workspace: {pattern}"
            )
        cleaned.append(pattern)
    return cleaned


def _verify_artifact_patterns(base_dir: str, patterns: list[str]) -> bool:
    """Return True when at least one glob pattern matches under ``base_dir``.

    Synchronous filesystem walk; call via ``asyncio.to_thread`` from the
    service layer. No patterns means nothing to verify (pass). Malformed
    or unreadable patterns report ``False`` (missing) instead of raising.
    """
    if not patterns:
        return True
    root = Path(base_dir)
    if not root.is_dir():
        return False
    try:
        for pattern in patterns:
            if any(root.glob(pattern)):
                return True
    except (OSError, ValueError, NotImplementedError):
        # Unreadable tree or unsupported pattern (e.g. absolute-path glob)
        return False
    return False


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
        "artifact_patterns": (
            list(p.artifact_patterns_json) if p.artifact_patterns_json else []
        ),
        "total_tasks": p.total_tasks,
        "completed_tasks": p.completed_tasks,
        "failed_tasks": p.failed_tasks,
        "failed_directories": [],
        "missing_artifact_directories": [],
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
        stmt = (
            select(KanbanTaskModel)
            .where(
                KanbanTaskModel.metadata_json["batch_project_id"].as_string()
                == project_id
            )
            .order_by(KanbanTaskModel.created_at)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


def _aggregate_statuses(tasks: list[KanbanTaskModel]) -> tuple[int, int, int]:
    """Return (total, completed, failed) counts from the given tasks."""
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED.value)
    failed = sum(
        1
        for t in tasks
        if t.status in (TaskStatus.FAILED.value, TaskStatus.ARCHIVED.value)
    )
    return total, completed, failed


async def _send_completion_notification(
    project_id: str,
    status: str,
    total: int,
    completed: int,
    failed: int,
    missing_artifact_directories: list[str] | None = None,
) -> None:
    async with get_session() as session:
        model = await session.get(BatchDirectoryProjectModel, project_id)
        project_name = model.name if model is not None else project_id

    from app.services.infra.system_notification import SystemNotificationService

    missing = missing_artifact_directories or []
    if status == "completed":
        title = f"Batch complete: {project_name}"
        message = f"{completed}/{total} directories completed."
    else:
        title = f"Batch finished with failures: {project_name}"
        message = f"{completed} completed, {failed} failed of {total} directories."
    if missing:
        dir_word = "directory" if len(missing) == 1 else "directories"
        message += f" {len(missing)} {dir_word} missing required artifacts."
    await SystemNotificationService.create_notification(
        title=title,
        message=message,
        type="info",
        source="batch_directory",
        meta_data={
            "project_id": project_id,
            "status": status,
            "total": total,
            "completed": completed,
            "failed": failed,
            "missing_artifact_directories": missing,
            "action_url": f"/batch-directories/{project_id}",
        },
    )
