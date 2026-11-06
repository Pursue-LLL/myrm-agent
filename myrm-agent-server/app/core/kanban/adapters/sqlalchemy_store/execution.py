"""[INPUT]
- .common (POS: shared types and helpers)

[OUTPUT]
- ExecutionMixin

[POS]
SqlAlchemyKanbanStore mixin: task claiming, status transitions, heartbeat, zombie/scheduled scans.
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.kanban.types import (
    _PRIORITY_ORDER,
    KanbanTask,
    TaskStatus,
)
from sqlalchemy import func as sqlfunc
from sqlalchemy import or_, select, update

from app.core.kanban.adapters.sqlalchemy_mapping import (
    status_change_values,
    task_to_domain,
)
from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanTaskModel,
)

from .common import (
    _exec_rowcount,
)


class ExecutionMixin:
    async def claim_task(self, task_id: str, worker_id: str) -> bool:
        now = datetime.now(UTC)
        async with get_session() as session:
            stmt = (
                update(KanbanTaskModel)
                .where(
                    KanbanTaskModel.id == task_id,
                    KanbanTaskModel.status == TaskStatus.READY.value,
                )
                .values(
                    status=TaskStatus.RUNNING.value,
                    last_heartbeat_at=now,
                )
            )
            result = await session.execute(stmt)
            if _exec_rowcount(result) == 0:
                await session.rollback()
                return False

            # Store worker_id in metadata (separate read to stay within the
            # same transaction after the atomic status flip).
            m = await session.get(KanbanTaskModel, task_id)
            if m is not None:
                merged = dict(m.metadata_json) if m.metadata_json else {}
                merged["worker_id"] = worker_id
                m.metadata_json = merged

            await session.commit()
            return True

    async def transition_task_status(
        self,
        task_id: str,
        expected_status: TaskStatus,
        new_status: TaskStatus,
    ) -> KanbanTask | None:
        async with get_session() as session:
            stmt = (
                update(KanbanTaskModel)
                .where(
                    KanbanTaskModel.id == task_id,
                    KanbanTaskModel.status == expected_status.value,
                )
                .values(**status_change_values(new_status))
            )
            result = await session.execute(stmt)
            if _exec_rowcount(result) == 0:
                await session.rollback()
                return None
            await session.commit()
            m = await session.get(KanbanTaskModel, task_id)
            return task_to_domain(m) if m else None

    async def list_ready_tasks(self, board_id: str) -> list[KanbanTask]:
        async with get_session() as session:
            stmt = (
                select(KanbanTaskModel)
                .where(
                    KanbanTaskModel.board_id == board_id,
                    KanbanTaskModel.status == TaskStatus.READY.value,
                )
                .order_by(KanbanTaskModel.created_at)
            )
            result = await session.execute(stmt)
            tasks = [task_to_domain(m) for m in result.scalars().all()]
            tasks.sort(key=lambda t: (_PRIORITY_ORDER.get(t.priority, 2), t.created_at))
            return tasks

    async def list_running_tasks(self, board_id: str) -> list[KanbanTask]:
        async with get_session() as session:
            stmt = select(KanbanTaskModel).where(
                KanbanTaskModel.board_id == board_id,
                KanbanTaskModel.status == TaskStatus.RUNNING.value,
            )
            result = await session.execute(stmt)
            return [task_to_domain(m) for m in result.scalars().all()]

    async def update_heartbeat(self, task_id: str, *, note: str | None = None) -> None:
        values: dict[str, object] = {"last_heartbeat_at": datetime.now(UTC)}
        if note is not None:
            values["progress_note"] = note
        async with get_session() as session:
            stmt = (
                update(KanbanTaskModel)
                .where(
                    KanbanTaskModel.id == task_id,
                    KanbanTaskModel.status == TaskStatus.RUNNING.value,
                )
                .values(**values)
            )
            await session.execute(stmt)
            await session.commit()

    async def list_zombie_tasks(self, board_id: str, timeout_seconds: int) -> list[KanbanTask]:
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        async with get_session() as session:
            stmt = select(KanbanTaskModel).where(
                KanbanTaskModel.board_id == board_id,
                KanbanTaskModel.status == TaskStatus.RUNNING.value,
                or_(
                    KanbanTaskModel.last_heartbeat_at.is_(None),
                    KanbanTaskModel.last_heartbeat_at < cutoff,
                ),
            )
            result = await session.execute(stmt)
            return [task_to_domain(m) for m in result.scalars().all()]

    async def list_due_scheduled_tasks(self, board_id: str) -> list[KanbanTask]:
        now = datetime.now(UTC)
        async with get_session() as session:
            stmt = select(KanbanTaskModel).where(
                KanbanTaskModel.board_id == board_id,
                KanbanTaskModel.status == TaskStatus.BLOCKED.value,
                KanbanTaskModel.block_kind == "scheduled",
                KanbanTaskModel.scheduled_until.isnot(None),
                KanbanTaskModel.scheduled_until <= now,
            )
            result = await session.execute(stmt)
            return [task_to_domain(m) for m in result.scalars().all()]

    async def earliest_scheduled_until(self, after: datetime) -> datetime | None:
        """Earliest auto-unblock time strictly after ``after`` among scheduled-blocked tasks of every board."""
        async with get_session() as session:
            result = await session.execute(
                select(sqlfunc.min(KanbanTaskModel.scheduled_until)).where(
                    KanbanTaskModel.status == TaskStatus.BLOCKED.value,
                    KanbanTaskModel.block_kind == "scheduled",
                    KanbanTaskModel.scheduled_until > after,
                )
            )
            earliest = result.scalar()
            if earliest is not None and earliest.tzinfo is None:
                return earliest.replace(tzinfo=UTC)
            return earliest

    async def reset_stale_running_tasks(self) -> int:
        """Reset all RUNNING tasks back to READY (boot recovery).

        Called on server startup to reclaim tasks that were mid-execution
        when the process exited.  Returns the number of tasks reset.
        """
        async with get_session() as session:
            stmt = (
                update(KanbanTaskModel)
                .where(KanbanTaskModel.status == TaskStatus.RUNNING.value)
                .values(
                    status=TaskStatus.READY.value,
                    last_heartbeat_at=None,
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return _exec_rowcount(result)
