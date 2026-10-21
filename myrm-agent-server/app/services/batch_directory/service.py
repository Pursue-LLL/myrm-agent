"""Batch directory parallel prompt runner — business service.

[INPUT]
- app.services.kanban::KanbanService (POS: Kanban 业务编排，任务执行完全委托)
- app.database.models.batch_directory::BatchDirectoryProjectModel (POS: 批量项目持久化)
- app.services.batch_directory._helpers (POS: 序列化/查询/路径校验助手)
- app.services.batch_directory._read (POS: 只读聚合层)
- app.services.batch_directory._retry (POS: 重试/重跑层)
- app.services.batch_directory._lifecycle (POS: 暂停/恢复/审批层)

[OUTPUT]
- BatchDirectoryService: 批量项目编排（创建/列表/详情/取消/删除/完成检测/重试/重跑）

[POS]
BatchDirectory 业务编排层。批量项目是 Kanban 任务的轻量编排器：
创建时把同一条 prompt 广播到 N 个目录（每目录一个 Kanban 任务），
执行 100% 委托 Kanban dispatcher/runner，本项目仅聚合进度、校验产物与通知。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.types import BoardSettings, TaskStatus
from sqlalchemy import update as sa_update

from app.database.connection import get_session
from app.database.models.batch_directory import BatchDirectoryProjectModel
from app.services.batch_directory import _lifecycle, _read, _retry
from app.services.batch_directory._helpers import (
    _PROJECT_TERMINAL_STATUSES,
    _TERMINAL_STATUSES,
    _aggregate_statuses,
    _failed_directory_paths,
    _latest_tasks_per_directory,
    _now,
    _project_to_dict,
    _resolve_directory,
    _send_completion_notification,
    _validate_artifact_patterns,
    fetch_project_task_models,
)
from app.services.batch_directory._read import _resolve_artifact_results
from app.services.batch_directory._run import fan_out_batch_tasks

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.kanban.types import KanbanTask

    from app.services.kanban import KanbanService

logger = logging.getLogger(__name__)

# dispatcher 终态事件名（触发项目完成检测）
_FINAL_EVENTS = frozenset({"task_completed", "task_failed", "task_blocked", "task_archived"})


class BatchDirectoryService:
    """Singleton orchestration service for batch directory projects."""

    _instance: BatchDirectoryService | None = None

    def __init__(self) -> None:
        self._kanban: KanbanService | None = None  # lazy: KanbanService.get_instance()

    @classmethod
    def get_instance(cls) -> BatchDirectoryService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def kanban(self) -> KanbanService:
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
        artifact_patterns = _validate_artifact_patterns(artifact_patterns)

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
        created, errors = await fan_out_batch_tasks(
            self.kanban,
            board_id=target_board_id,
            project_id=project_id,
            name=name,
            prompt=prompt,
            directories=resolved_dirs,
            agent_id=agent_id,
            model_override=model_override,
            max_runtime_seconds=max_runtime_seconds,
            require_approval=require_approval,
            artifact_patterns=artifact_patterns,
        )
        if errors:
            # 原子创建：任一目录建任务失败即整体失败，回滚已建任务，
            # 避免批次静默丢弃目录（无任务目录既不可见也不可重试）。
            for tid in created:
                try:
                    await self.kanban.move_task(
                        tid,
                        TaskStatus.ARCHIVED,
                        result="",
                        metadata={"aborted_by": "batch_creation_failed"},
                    )
                except Exception as exc:  # noqa: BLE001 - 回滚失败不掩盖根因
                    logger.warning(
                        "Batch project %s: rollback task %s failed: %s",
                        project_id,
                        tid,
                        exc,
                    )
            raise ValueError(
                "Failed to create batch tasks for some directories: " + "; ".join(f"{d}: {e}" for d, e in errors[:3])
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
        return result

    # ------------------------------------------------------------------
    # Read (aggregation in _read.py)
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[dict[str, object]]:
        return await _read.list_projects(self)

    async def get_project(self, project_id: str) -> dict[str, object] | None:
        return await _read.get_project(self, project_id)

    # ------------------------------------------------------------------
    # Cancel / delete
    # ------------------------------------------------------------------

    async def cancel_project(self, project_id: str) -> dict[str, object] | None:
        """Cancel all non-terminal tasks of a project.

        The project is atomically marked ``cancelled`` first: archiving tasks
        fires ``task_archived`` dispatcher events, and a concurrent
        ``maybe_finalize`` must observe the terminal status and skip instead of
        misreporting a failure. Running tasks are then cancelled in the
        dispatcher (stops agent execution promptly, no wasted compute); tasks
        awaiting approval are rejected before archiving (manual moves out of
        IN_REVIEW are guarded by the orchestrator). Non-terminal tasks are
        then archived.
        """
        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            if model is None:
                return None
            if model.status not in _PROJECT_TERMINAL_STATUSES:
                await session.execute(
                    sa_update(BatchDirectoryProjectModel)
                    .where(
                        BatchDirectoryProjectModel.id == project_id,
                        BatchDirectoryProjectModel.status.notin_(list(_PROJECT_TERMINAL_STATUSES)),
                    )
                    .values(status="cancelled", finished_at=_now())
                )
                await session.commit()

        tasks = await fetch_project_task_models(project_id)
        cancelled: list[str] = []
        for t in tasks:
            status = TaskStatus(t.status) if t.status else None
            if status is None or status in _TERMINAL_STATUSES:
                continue
            try:
                if status == TaskStatus.RUNNING:
                    await self.kanban.cancel_task_execution(t.id)
                elif status == TaskStatus.IN_REVIEW:
                    await self.kanban.reject_task(t.id, reason="Batch project cancelled")
                await self.kanban.move_task(
                    t.id,
                    TaskStatus.ARCHIVED,
                    result="",
                    metadata={"cancelled_by": "batch_project"},
                )
                cancelled.append(t.id)
            except Exception as exc:  # noqa: BLE001 - 单任务取消失败不阻断
                logger.warning("Batch project %s: cancel task %s failed: %s", project_id, t.id, exc)

        base = await self.get_project(project_id)
        if base is None:
            return None
        base["cancelled_task_ids"] = cancelled
        return base

    # Retry / rerun (logic in _retry.py), pause / resume / approve-all (in _lifecycle.py)

    async def retry_failed(self, project_id: str) -> dict[str, object] | None:
        return await _retry.retry_failed(self, project_id)

    async def retry_task(self, project_id: str, task_id: str) -> dict[str, object] | None:
        return await _retry.retry_task(self, project_id, task_id)

    async def rerun_project(self, project_id: str) -> dict[str, object] | None:
        return await _retry.rerun_project(self, project_id)

    async def pause_project(self, project_id: str) -> dict[str, object] | None:
        return await _lifecycle.pause_project(self, project_id)

    async def resume_project(self, project_id: str) -> dict[str, object] | None:
        return await _lifecycle.resume_project(self, project_id)

    async def approve_all_results(self, project_id: str) -> dict[str, object] | None:
        return await _lifecycle.approve_all_results(self, project_id)

    async def delete_project(self, project_id: str) -> bool:
        tasks = await fetch_project_task_models(project_id)
        if any(t.status not in {s.value for s in _TERMINAL_STATUSES} for t in tasks):
            raise ValueError("Batch project still has running tasks; cancel it before deleting")
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
        update the project status and emit a completion notification.

        Atomic conditional UPDATE makes concurrent dispatcher callbacks
        idempotent — exactly one caller wins the status transition and sends
        the notification; losers observe the terminal status and skip.
        """
        async with get_session() as session:
            model = await session.get(BatchDirectoryProjectModel, project_id)
            if model is None:
                return
            if model.status in _PROJECT_TERMINAL_STATUSES or model.status == "paused":
                return  # 已终态（避免重复通知）或已暂停（冻结稳定，恢复后再判定）
            notify_enabled = model.notify_enabled

        tasks = await fetch_project_task_models(project_id)
        if not tasks:
            return
        latest = _latest_tasks_per_directory(tasks)

        pending = [t for t in latest if t.status not in {s.value for s in _TERMINAL_STATUSES}]
        if pending:
            return  # 仍有未终态任务

        total, completed, failed = _aggregate_statuses(latest)
        final_status = "completed" if failed == 0 else "failed"
        _, missing_artifacts = await _resolve_artifact_results(latest)

        async with get_session() as session:
            result = await session.execute(
                sa_update(BatchDirectoryProjectModel)
                .where(
                    BatchDirectoryProjectModel.id == project_id,
                    BatchDirectoryProjectModel.status.notin_(list(_PROJECT_TERMINAL_STATUSES)),
                )
                .values(
                    status=final_status,
                    completed_tasks=completed,
                    failed_tasks=failed,
                    total_tasks=total,
                    finished_at=_now(),
                )
            )
            await session.commit()
            finalized = result.rowcount > 0

        if finalized and notify_enabled:
            await _send_completion_notification(
                project_id,
                final_status,
                total,
                completed,
                failed,
                missing_artifacts,
                failed_directories=_failed_directory_paths(latest),
            )

    # ------------------------------------------------------------------
    # Dispatcher event hook factory
    # ------------------------------------------------------------------

    def dispatcher_event_hook(self, event_type: str, task: KanbanTask) -> None:
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
