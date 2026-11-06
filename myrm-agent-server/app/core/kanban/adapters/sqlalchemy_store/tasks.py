"""[INPUT]
- .common (POS: shared types and helpers)

[OUTPUT]
- TasksMixin

[POS]
SqlAlchemyKanbanStore mixin: task CRUD, listing/counting, card stats and active-branch metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.kanban.types import (
    _TERMINAL_STATUSES,
    KANBAN_SOURCE_CHAT_METADATA_KEY,
    KanbanTask,
    TaskEventKind,
    TaskStatus,
)
from sqlalchemy import func as sqlfunc
from sqlalchemy import select

from app.core.kanban.adapters.sqlalchemy_mapping import (
    apply_task_to_model,
    task_to_domain,
    task_to_model,
)
from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanTaskEdgeModel,
    KanbanTaskEventModel,
    KanbanTaskModel,
)

from .common import (
    TaskCardStats,
)


class TasksMixin:
    async def update_active_tasks_branch_metadata(
        self,
        new_branch: str,
        old_branch: str | None = None,
        migrated: bool = False,
        board_id: str | None = None,
    ) -> list[KanbanTask]:
        """Update branch metadata for all active tasks across all boards (or a specific board) and append branch_switched event."""
        import datetime

        from sqlalchemy import select

        from app.database.models.kanban import KanbanTaskEventModel, KanbanTaskModel

        async with get_session() as session:
            stmt = select(KanbanTaskModel).where(
                KanbanTaskModel.status.in_(
                    [
                        TaskStatus.BACKLOG,
                        TaskStatus.READY,
                        TaskStatus.RUNNING,
                        TaskStatus.BLOCKED,
                    ]
                )
            )
            if board_id:
                stmt = stmt.where(KanbanTaskModel.board_id == board_id)

            result = await session.execute(stmt)
            tasks = result.scalars().all()

            updated_tasks = []
            for task in tasks:
                meta = dict(task.metadata_json) if task.metadata_json else {}
                if meta.get("branch") != new_branch:
                    meta["branch"] = new_branch
                    task.metadata_json = meta
                    updated_tasks.append(task)

                # Append event
                event = KanbanTaskEventModel(
                    task_id=task.id,
                    kind=TaskEventKind.BRANCH_SWITCHED.value,
                    payload_json={
                        "from": old_branch,
                        "to": new_branch,
                        "migrated": migrated,
                    },
                    created_at=datetime.datetime.now(datetime.UTC),
                )
                session.add(event)

            if tasks:
                await session.commit()
                for task in updated_tasks:
                    await session.refresh(task)
                from app.core.kanban.adapters.sqlalchemy_mapping import task_to_domain

                return [task_to_domain(t) for t in updated_tasks]
            return []

    async def get_task(self, task_id: str) -> KanbanTask | None:
        async with get_session() as session:
            m = await session.get(KanbanTaskModel, task_id)
            return task_to_domain(m) if m else None

    async def list_tasks(
        self,
        board_id: str,
        *,
        status: TaskStatus | None = None,
        parent_task_id: str | None = None,
        agent_id: str | None = None,
        source_chat_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[KanbanTask]:
        async with get_session() as session:
            stmt = select(KanbanTaskModel).where(KanbanTaskModel.board_id == board_id)
            if status is not None:
                stmt = stmt.where(KanbanTaskModel.status == status.value)
            if parent_task_id is not None:
                stmt = stmt.where(KanbanTaskModel.parent_task_id == parent_task_id)
            if agent_id is not None:
                stmt = stmt.where(KanbanTaskModel.agent_id == agent_id)
            if source_chat_id is not None:
                stmt = stmt.where(KanbanTaskModel.metadata_json[KANBAN_SOURCE_CHAT_METADATA_KEY].as_string() == source_chat_id)
            stmt = stmt.order_by(KanbanTaskModel.created_at)
            stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return [task_to_domain(m) for m in result.scalars().all()]

    async def count_tasks(
        self,
        board_id: str,
        *,
        status: TaskStatus | None = None,
    ) -> int:
        async with get_session() as session:
            stmt = select(sqlfunc.count()).select_from(KanbanTaskModel).where(KanbanTaskModel.board_id == board_id)
            if status is not None:
                stmt = stmt.where(KanbanTaskModel.status == status.value)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def batch_task_stats(
        self,
        task_ids: list[str],
    ) -> dict[str, TaskCardStats]:
        """Batch-fetch per-task stats for card badges (avoids N+1).

        Four aggregate queries: parent edge count, child edge count,
        terminal-child count, user_comment event count.
        Only queries stats for the given task_ids (typically the current page).
        """
        if not task_ids:
            return {}

        async with get_session() as session:
            stats: dict[str, TaskCardStats] = {tid: TaskCardStats(0, 0, 0, 0) for tid in task_ids}

            dep_stmt = (
                select(
                    KanbanTaskEdgeModel.child_task_id,
                    sqlfunc.count().label("cnt"),
                )
                .where(KanbanTaskEdgeModel.child_task_id.in_(task_ids))
                .group_by(KanbanTaskEdgeModel.child_task_id)
            )
            dep_result = await session.execute(dep_stmt)
            dep_map: dict[str, int] = {row[0]: row[1] for row in dep_result.all()}

            child_total_stmt = (
                select(
                    KanbanTaskEdgeModel.parent_task_id,
                    sqlfunc.count().label("total"),
                )
                .where(KanbanTaskEdgeModel.parent_task_id.in_(task_ids))
                .group_by(KanbanTaskEdgeModel.parent_task_id)
            )
            child_total_result = await session.execute(child_total_stmt)
            child_map: dict[str, tuple[int, int]] = {row[0]: (row[1], 0) for row in child_total_result.all()}

            child_done_stmt = (
                select(
                    KanbanTaskEdgeModel.parent_task_id,
                    sqlfunc.count().label("done"),
                )
                .join(
                    KanbanTaskModel,
                    KanbanTaskEdgeModel.child_task_id == KanbanTaskModel.id,
                )
                .where(
                    KanbanTaskEdgeModel.parent_task_id.in_(task_ids),
                    KanbanTaskModel.status.in_([s.value for s in _TERMINAL_STATUSES]),
                )
                .group_by(KanbanTaskEdgeModel.parent_task_id)
            )
            child_done_result = await session.execute(child_done_stmt)
            for row in child_done_result.all():
                total = child_map.get(row[0], (0, 0))[0]
                child_map[row[0]] = (total, row[1])

            comment_stmt = (
                select(
                    KanbanTaskEventModel.task_id,
                    sqlfunc.count().label("cnt"),
                )
                .where(
                    KanbanTaskEventModel.task_id.in_(task_ids),
                    KanbanTaskEventModel.kind == TaskEventKind.USER_COMMENT.value,
                )
                .group_by(KanbanTaskEventModel.task_id)
            )
            comment_result = await session.execute(comment_stmt)
            comment_map: dict[str, int] = {row[0]: row[1] for row in comment_result.all()}

            for tid in task_ids:
                dc = dep_map.get(tid, 0)
                ct, cd = child_map.get(tid, (0, 0))
                cc = comment_map.get(tid, 0)
                stats[tid] = TaskCardStats(dc, ct, cd, cc)

            return stats

    async def count_tasks_grouped(self, board_id: str) -> dict[str, int]:
        async with get_session() as session:
            stmt = (
                select(KanbanTaskModel.status, sqlfunc.count())
                .where(KanbanTaskModel.board_id == board_id)
                .group_by(KanbanTaskModel.status)
            )
            result = await session.execute(stmt)
            return {status: count for status, count in result.all()}

    async def count_tasks_by_agent(
        self,
        board_id: str,
    ) -> dict[str | None, dict[str, int]]:
        """Count non-archived tasks grouped by (agent_id, status)."""
        async with get_session() as session:
            stmt = (
                select(
                    KanbanTaskModel.agent_id,
                    KanbanTaskModel.status,
                    sqlfunc.count(),
                )
                .where(
                    KanbanTaskModel.board_id == board_id,
                    KanbanTaskModel.status != TaskStatus.ARCHIVED.value,
                )
                .group_by(KanbanTaskModel.agent_id, KanbanTaskModel.status)
            )
            result = await session.execute(stmt)
            by_agent: dict[str | None, dict[str, int]] = {}
            for agent_id, status, count in result.all():
                by_agent.setdefault(agent_id, {})[status] = count
            return by_agent

    async def oldest_ready_age_seconds(self, board_id: str) -> int | None:
        """Return seconds since the oldest READY task was last updated, or None."""
        async with get_session() as session:
            stmt = select(sqlfunc.min(KanbanTaskModel.updated_at)).where(
                KanbanTaskModel.board_id == board_id,
                KanbanTaskModel.status == TaskStatus.READY.value,
            )
            row = await session.execute(stmt)
            oldest = row.scalar_one_or_none()
            if oldest is None:
                return None
            now = datetime.now(UTC)
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=UTC)
            return int((now - oldest).total_seconds())

    async def count_stale_running_tasks(self, board_id: str, timeout_seconds: int) -> int:
        """Count RUNNING tasks whose heartbeat is older than timeout (zombie candidates)."""
        zombies = await self.list_zombie_tasks(board_id, timeout_seconds)
        return len(zombies)

    async def save_task(self, task: KanbanTask) -> KanbanTask:
        async with get_session() as session:
            existing = await session.get(KanbanTaskModel, task.task_id)
            if existing:
                apply_task_to_model(task, existing)
                await session.commit()
                await session.refresh(existing)
                return task_to_domain(existing)
            m = task_to_model(task)
            session.add(m)
            await session.commit()
            await session.refresh(m)
            return task_to_domain(m)

    async def delete_task(self, task_id: str) -> bool:
        async with get_session() as session:
            m = await session.get(KanbanTaskModel, task_id)
            if not m:
                return False
            await session.delete(m)
            await session.commit()
            return True
