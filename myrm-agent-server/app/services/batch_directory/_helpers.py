"""Batch directory serialization + query helpers.

[INPUT]
- app.database.models.batch_directory::BatchDirectoryProjectModel (POS: 批量项目持久化)
- myrm_agent_harness.agent.security.path_security::is_dangerous_path (POS: 路径安全校验)
- app.services.event.app_event_bus::get_event_bus (POS: SYSTEM_NOTIFICATION 事件总线，经通知投递/Web Push/WebUI 扇出)

[OUTPUT]
- fetch_project_task_models: 按 batch_project_id 查询任务（服务内复用）
- _latest_tasks_per_directory: 每目录取最新任务（重试后聚合口径）
- _project_to_dict / _aggregate_statuses / _resolve_directory: 序列化与校验助手
- _reopen_running: 项目回置 running 并刷新聚合（重试/重跑/恢复共用，支持 expected_status 条件更新防并发覆盖）
- _format_duration / _format_batch_summary: 耗时格式化与站内通知行/完成事件共享的批次结果正文（标题 + 统计行 + 耗时 + 失败目录列表/缺产物提示）
- _send_completion_notification: 批次终态站内通知行（携带 action_url 深链）+ 一次 SYSTEM_NOTIFICATION 事件
- _publish_completion_event: 把批次结果发布到系统通知管道（IM 与 Web Push 按用户的通知设置，WebUI 弹窗与铃铛随事件刷新）
- _PROJECT_TERMINAL_STATUSES / _BATCH_PAUSE_BLOCK_REASON / _BATCH_APPROVER: 批次终态与暂停/审批标记常量

[POS]
纯助手函数（无业务编排）。`_validate_artifact_patterns` 同时被 API schemas
直接引用做创建期校验，模块间无环形依赖。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from myrm_agent_harness.toolkits.kanban.types import TaskStatus
from sqlalchemy import select
from sqlalchemy import update as sa_update

from app.config.settings import settings
from app.database.connection import get_session
from app.database.models.batch_directory import BatchDirectoryProjectModel
from app.database.models.kanban import KanbanTaskModel
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)

# 任务终态：completed/failed/archived 视为不再由 dispatcher 调度
_TERMINAL_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED})
# 批量项目终态：到达后不再接受调度、可安全删除
_PROJECT_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
# 批次暂停冻结标记（写入任务的 blocked_reason，恢复时据此筛选）
_BATCH_PAUSE_BLOCK_REASON = "batch_pause"
_BATCH_APPROVER = "batch:approve-all"
# 站内通知行与完成事件中最多列出的失败目录数（防超长刷屏）
_MAX_FAILED_DIRECTORIES_IN_SUMMARY = 10


def _failed_directory_paths(tasks: list[KanbanTaskModel]) -> list[str]:
    """Return workspace paths of tasks that did not complete (failed/archived)."""
    return [
        str(t.workspace_path)
        for t in tasks
        if t.workspace_path and t.status in (TaskStatus.FAILED.value, TaskStatus.ARCHIVED.value)
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
    return "verified" if _verify_artifact_patterns(t.workspace_path, patterns) else "missing"


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
            raise ValueError(f"Artifact pattern must stay inside the workspace: {pattern}")
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
        "artifact_patterns": (list(p.artifact_patterns_json) if p.artifact_patterns_json else []),
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
            .where(KanbanTaskModel.metadata_json["batch_project_id"].as_string() == project_id)
            .order_by(KanbanTaskModel.created_at)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


def _aggregate_statuses(tasks: list[KanbanTaskModel]) -> tuple[int, int, int]:
    """Return (total, completed, failed) counts from the given tasks."""
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED.value)
    failed = sum(1 for t in tasks if t.status in (TaskStatus.FAILED.value, TaskStatus.ARCHIVED.value))
    return total, completed, failed


async def _reopen_running(project_id: str, *, expected_status: str | None = None) -> None:
    """Reopen a project to ``running`` and refresh aggregation counters.

    Shared by retry/rerun/resume entry points: after tasks are fanned out or
    unblocked, the counters are recomputed from the current task set (one per
    directory) and the finish timestamp is cleared. When ``expected_status``
    is given the UPDATE is conditional — the project only reopens if it is
    still in that status, so a concurrent state change (e.g. cancel) wins
    instead of being overwritten.
    """
    refreshed = await fetch_project_task_models(project_id)
    latest = _latest_tasks_per_directory(refreshed)
    total, completed, failed = _aggregate_statuses(latest)
    stmt = (
        sa_update(BatchDirectoryProjectModel)
        .where(BatchDirectoryProjectModel.id == project_id)
        .values(
            status="running",
            total_tasks=total,
            completed_tasks=completed,
            failed_tasks=failed,
            finished_at=None,
        )
    )
    if expected_status is not None:
        stmt = stmt.where(BatchDirectoryProjectModel.status == expected_status)
    async with get_session() as session:
        await session.execute(stmt)
        await session.commit()


def _format_duration(seconds: int) -> str:
    """Format a wall-clock duration compactly: 42s / 8m 30s / 1h 5m."""
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s" if sec else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def _format_batch_summary(
    *,
    status: str,
    project_name: str,
    total: int,
    completed: int,
    failed: int,
    missing: list[str],
    failed_directories: Sequence[str] = (),
    duration_seconds: int | None = None,
) -> tuple[str, str]:
    """Return (title, summary lines) for a finished batch project.

    Both the in-app notification row (title + message) and the completion
    event share this wording so the surfaces stay consistent. ``missing``
    lists directories that completed without their declared artifacts;
    ``failed_directories`` names the directories that did not complete
    (truncated to keep the message short); ``duration_seconds`` reports the
    wall-clock runtime (omitted when unknown).
    """
    if status == "completed":
        title = f"Batch complete: {project_name}"
        lines = [f"{completed}/{total} directories completed."]
    else:
        title = f"Batch finished with failures: {project_name}"
        lines = [f"{completed} completed, {failed} failed of {total} directories."]
        if failed_directories:
            lines.append("Failed directories:")
            lines.extend(f"- {d}" for d in failed_directories[:_MAX_FAILED_DIRECTORIES_IN_SUMMARY])
            hidden = len(failed_directories) - _MAX_FAILED_DIRECTORIES_IN_SUMMARY
            if hidden > 0:
                lines.append(f"... and {hidden} more")
    if duration_seconds is not None:
        lines.append(f"Duration: {_format_duration(duration_seconds)}")
    if missing:
        dir_word = "directory" if len(missing) == 1 else "directories"
        lines.append(f"{len(missing)} {dir_word} missing required artifacts.")
    return title, "\n".join(lines)


async def _send_completion_notification(
    project_id: str,
    status: str,
    total: int,
    completed: int,
    failed: int,
    missing_artifact_directories: list[str] | None = None,
    failed_directories: list[str] | None = None,
) -> None:
    """Record the result in the in-app list, then announce it once on the notification pipeline."""
    async with get_session() as session:
        model = await session.get(BatchDirectoryProjectModel, project_id)
        project_name = model.name if model is not None else project_id
        duration_seconds: int | None = None
        if model is not None and model.started_at is not None and model.finished_at is not None:
            duration_seconds = max(0, int((model.finished_at - model.started_at).total_seconds()))

    from app.services.infra.system_notification import SystemNotificationService

    missing = missing_artifact_directories or []
    title, message = _format_batch_summary(
        status=status,
        project_name=project_name,
        total=total,
        completed=completed,
        failed=failed,
        missing=missing,
        failed_directories=failed_directories or [],
        duration_seconds=duration_seconds,
    )
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
            "failed_directories": failed_directories or [],
            "action_url": f"/batch-directories/{project_id}",
        },
    )
    _publish_completion_event(project_id=project_id, status=status, title=title, message=message)


def _publish_completion_event(*, project_id: str, status: str, title: str, message: str) -> None:
    """Announce a finished batch on the system notification pipeline.

    The pipeline delivers it to what the user configured (notification deliveries for IM, Web Push, the in-app
    toast and bell), so the batch never picks recipients. ``level`` colours the toast. ``project_id`` makes each
    payload unique: the bus drops an event identical to the one before it, which would swallow the second of two
    projects with equal names and results. A details link is only added when ``APP_BASE_URL`` makes it absolute,
    since a relative path means nothing outside the app. The terminal status is already committed, so a failed
    publish is logged and dropped.
    """
    base_url = settings.app_base_url.strip().rstrip("/")
    body = f"{message}\nDetails: {base_url}/batch-directories/{project_id}" if base_url else message
    try:
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.SYSTEM_NOTIFICATION,
                data={
                    "title": title,
                    "message": body,
                    "meta_data": {"level": "success" if status == "completed" else "warning", "project_id": project_id},
                },
            )
        )
    except Exception as exc:
        logger.warning("Failed to publish batch completion event for project %s: %s", project_id, exc)
