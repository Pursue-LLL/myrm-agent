"""Batch directory parallel prompt runner — business service.

[INPUT]
- app.services.kanban::KanbanService (POS: Kanban 业务编排，任务执行完全委托)
- app.database.models.batch_directory::BatchDirectoryProjectModel (POS: 批量项目持久化)
- myrm_agent_harness.agent.security.path_security::is_dangerous_path (POS: 路径安全校验)

[OUTPUT]
- BatchDirectoryService: 批量项目编排（创建/列表/详情/取消/删除/完成检测）
- fetch_project_task_models: 按 batch_project_id 查询任务（服务内复用）

[POS]
BatchDirectory 业务编排层。批量项目是 Kanban 任务的轻量编排器：
创建时把同一条 prompt 广播到 N 个目录（每目录一个 Kanban 任务），
执行 100% 委托 Kanban dispatcher/runner，本项目仅聚合进度、校验产物与通知。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

from myrm_agent_harness.toolkits.kanban.types import TaskPriority, TaskStatus
from sqlalchemy import select

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.database.connection import get_session
from app.database.models.batch_directory import BatchDirectoryProjectModel
from app.database.models.kanban import KanbanTaskModel

logger = logging.getLogger(__name__)

TerminalCallback = Callable[[str], Awaitable[None]]

# 任务终态：completed/failed/archived 视为不再由 dispatcher 调度
_TERMINAL_STATUSES = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED}
)
# dispatcher 终态事件名（触发项目完成检测）
_FINAL_EVENTS = frozenset({"task_completed", "task_failed", "task_blocked"})


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


class BatchDirectoryService:
    """Singleton orchestration service for batch directory projects."""

    _instance: BatchDirectoryService | None = None

    def __init__(self) -> None:
        self._kanban = None  # lazy: KanbanService.get_instance()

    @classmethod
    def get_instance(cls) -> BatchDirectoryService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def kanban(self):
        if self._kanban is None:
            from app.services.kanban import KanbanService

            self._kanban = KanbanService.get_instance()
        return self._kanban

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_project(
        self,
        *,
        name: str,
        prompt: str,
        directories: list[str],
        board_id: str | None = None,
        concurrency: int = 3,
        agent_id: str | None = None,
        model_override: str | None = None,
        max_runtime_seconds: int | None = None,
        require_approval: bool = False,
        notify_enabled: bool = True,
        artifact_patterns: list[str] | None = None,
    ) -> dict[str, object]:
        if not name.strip():
            raise ValueError("Project name is required")
        if not prompt.strip():
            raise ValueError("Prompt is required")
        if not directories:
            raise ValueError("At least one target directory is required")

        # 去重 + 校验目录存在且安全
        seen: set[str] = set()
        resolved_dirs: list[str] = []
        for raw in directories:
            resolved = _resolve_directory(raw)
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            resolved_dirs.append(key)
        if not resolved_dirs:
            raise ValueError("No valid target directories provided")

        project_id = uuid.uuid4().hex[:12]

        # 解析目标 board：未指定则自动创建（并设置并发上限）
        target_board_id = board_id
        if not target_board_id:
            from myrm_agent_harness.toolkits.kanban.types import BoardSettings

            board = await self.kanban.create_board(
                name=f"{name.strip()} (Batch)",
                description=f"Batch directory project: {name.strip()}",
                settings=BoardSettings(
                    max_concurrent_tasks=max(1, min(int(concurrency), 50)),
                ),
            )
            target_board_id = board.board_id
        else:
            board = await self.kanban.get_board(target_board_id)
            if board is None:
                raise ValueError(f"Board {target_board_id} not found")

        project_model = BatchDirectoryProjectModel(
            id=project_id,
            name=name.strip(),
            prompt=prompt.strip(),
            board_id=target_board_id,
            status="draft",
            concurrency=max(1, min(int(concurrency), 50)),
            agent_id=agent_id,
            model_override=model_override,
            max_runtime_seconds=max_runtime_seconds,
            require_approval=require_approval,
            notify_enabled=notify_enabled,
            directories_json=resolved_dirs,
            artifact_patterns_json=artifact_patterns or None,
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
        )

        # 每目录创建一条 Kanban 任务（workspace_path=目录，metadata 标记 batch_project_id）
        created: list[str] = []
        errors: list[tuple[str, str]] = []
        for index, directory in enumerate(resolved_dirs):
            title = f"[{name.strip()}] {Path(directory).name or directory}"
            try:
                task = await self.kanban.add_task(
                    board_id=target_board_id,
                    title=title,
                    description=prompt.strip(),
                    priority=TaskPriority.NORMAL,
                    agent_id=agent_id,
                    model_override=model_override,
                    max_runtime_seconds=max_runtime_seconds,
                    require_approval=require_approval,
                    initial_status=TaskStatus.READY,
                    workspace_path=directory,
                    metadata_patch={
                        "batch_project_id": project_id,
                        "batch_project_name": name.strip(),
                        "batch_directory": directory,
                        "batch_index": index,
                    },
                )
                created.append(task.task_id)
            except Exception as exc:  # noqa: BLE001 - 单目录失败不阻断整批
                logger.warning(
                    "Batch project %s: failed to create task for %s: %s",
                    project_id,
                    directory,
                    exc,
                )
                errors.append((directory, str(exc)))

        if not created:
            raise ValueError(
                "All target directories failed task creation: "
                + "; ".join(f"{d}: {e}" for d, e in errors[:3])
            )

        async with get_session() as session:
            project_model.total_tasks = len(created)
            project_model.status = "running"
            project_model.started_at = _now()
            session.add(project_model)
            await session.commit()
            await session.refresh(project_model)

        result = _project_to_dict(project_model)
        result["created_task_ids"] = created
        result["failed_directories"] = [d for d, _ in errors]
        return result

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[dict[str, object]]:
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
            from sqlalchemy import or_

            stmt = select(KanbanTaskModel).where(
                or_(
                    *[
                        KanbanTaskModel.metadata_json["batch_project_id"].as_string() == pid
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
            total, completed, failed = _aggregate_statuses(tasks)
            d["total_tasks"] = total if total else p.total_tasks
            d["completed_tasks"] = completed if total else p.completed_tasks
            d["failed_tasks"] = failed if total else p.failed_tasks
            items.append(d)
        return items

    async def get_project(self, project_id: str) -> dict[str, object] | None:
        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            if model is None:
                return None
            base = _project_to_dict(model)

        tasks = await fetch_project_task_models(project_id)
        total, completed, failed = _aggregate_statuses(tasks)
        base["total_tasks"] = total if total else model.total_tasks
        base["completed_tasks"] = completed if total else model.completed_tasks
        base["failed_tasks"] = failed if total else model.failed_tasks
        base["tasks"] = [
            {
                "task_id": t.id,
                "title": t.title,
                "status": t.status,
                "workspace_path": t.workspace_path,
                "agent_id": t.agent_id,
                "result": t.result,
                "error": t.error,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ]
        return base

    # ------------------------------------------------------------------
    # Cancel / delete
    # ------------------------------------------------------------------

    async def cancel_project(self, project_id: str) -> dict[str, object] | None:
        """Cancel all non-terminal tasks of a project (archive them)."""
        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            if model is None:
                return None
            base = _project_to_dict(model)

        tasks = await fetch_project_task_models(project_id)
        cancelled: list[str] = []
        for t in tasks:
            status = TaskStatus(t.status) if t.status else None
            if status is None or status in _TERMINAL_STATUSES:
                continue
            try:
                await self.kanban.move_task(
                    t.id,
                    TaskStatus.ARCHIVED,
                    result="",
                    metadata={"cancelled_by": "batch_project"},
                )
                cancelled.append(t.id)
            except Exception as exc:  # noqa: BLE001 - 单任务取消失败不阻断
                logger.warning("Batch project %s: cancel task %s failed: %s", project_id, t.id, exc)

        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            if model is not None:
                model.status = "cancelled"
                model.finished_at = _now()
                await session.commit()
                await session.refresh(model)
                base = _project_to_dict(model)

        base["cancelled_task_ids"] = cancelled
        return base

    async def delete_project(self, project_id: str) -> bool:
        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            if model is None:
                return False
            await session.delete(model)
            await session.commit()
        return True

    # ------------------------------------------------------------------
    # Terminal detection (dispatcher event hook)
    # ------------------------------------------------------------------

    async def maybe_finalize(self, project_id: str) -> None:
        """Check whether all project tasks reached a terminal state; if so,
        update the project status and emit a completion notification."""
        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            if model is None:
                return
            if model.status in ("completed", "failed", "cancelled"):
                return  # 已终态，避免重复通知

        tasks = await fetch_project_task_models(project_id)
        if not tasks:
            return

        pending = [t for t in tasks if t.status not in {s.value for s in _TERMINAL_STATUSES}]
        if pending:
            return  # 仍有未终态任务

        total, completed, failed = _aggregate_statuses(tasks)
        final_status = "completed" if failed == 0 else "failed"
        notify = False
        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            if model is not None:
                was_terminal = model.status in ("completed", "failed", "cancelled")
                if not was_terminal:
                    notify = model.notify_enabled
                model.status = final_status
                model.completed_tasks = completed
                model.failed_tasks = failed
                model.total_tasks = total
                model.finished_at = _now()
                await session.commit()

        if notify:
            await self._send_completion_notification(project_id, final_status, total, completed, failed)

    async def _send_completion_notification(
        self,
        project_id: str,
        status: str,
        total: int,
        completed: int,
        failed: int,
    ) -> None:
        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            project_name = model.name if model is not None else project_id

        from app.services.infra.system_notification import SystemNotificationService

        if status == "completed":
            title = f"✅ Batch complete: {project_name}"
            message = f"{completed}/{total} directories completed."
        else:
            title = f"⚠️ Batch finished with failures: {project_name}"
            message = f"{completed} completed, {failed} failed of {total} directories."
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
            },
        )

    # ------------------------------------------------------------------
    # Dispatcher event hook factory
    # ------------------------------------------------------------------

    def dispatcher_event_hook(self, event_type: str, task) -> None:
        """Synchronous dispatcher callback; schedules async finalize check.

        Registered in ``start_dispatcher`` so every board carrying batch
        tasks triggers terminal detection without polling.
        """
        if event_type not in _FINAL_EVENTS:
            return
        meta = getattr(task, "metadata", None) or {}
        project_id = meta.get("batch_project_id")
        if not project_id:
            return
        try:
            asyncio.get_running_loop().create_task(self.maybe_finalize(str(project_id)))
        except RuntimeError:  # pragma: no cover - 无事件循环时不调度
            logger.debug("No running loop; skip batch finalize for %s", project_id)
