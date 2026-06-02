"""SQLAlchemy implementation of the KanbanStore protocol.

CRUD operations for boards, tasks, runs, events, and dependency edges (DAG).
ORM mapping is delegated to ``sqlalchemy_mapping``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import NamedTuple

from myrm_agent_harness.toolkits.kanban.types import (
    _PRIORITY_ORDER,
    _TERMINAL_STATUSES,
    KanbanBoard,
    KanbanTask,
    TaskEdge,
    TaskEvent,
    TaskEventKind,
    TaskRun,
    TaskRunOutcome,
    TaskStatus,
)
from sqlalchemy import delete as sql_delete
from sqlalchemy import exists, or_, select, update
from sqlalchemy import func as sqlfunc

from app.core.kanban.adapters.sqlalchemy_mapping import (
    apply_board_to_model,
    apply_task_to_model,
    board_to_domain,
    board_to_model,
    task_to_domain,
    task_to_model,
)
from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanBoardModel,
    KanbanTaskEdgeModel,
    KanbanTaskEventModel,
    KanbanTaskModel,
    KanbanTaskRunModel,
)


class TaskCardStats(NamedTuple):
    """Per-task aggregate stats for card badges."""
    dep_count: int
    children_total: int
    children_done: int
    comment_count: int


def _exec_rowcount(result: object) -> int:
    rc = getattr(result, "rowcount", None)
    return rc if isinstance(rc, int) else 0


class SqlAlchemyKanbanStore:
    """KanbanStore backed by SQLAlchemy + app.database models."""

    # -- Board CRUD --

    async def update_active_tasks_branch_metadata(self, new_branch: str, old_branch: str | None = None, migrated: bool = False, board_id: str | None = None) -> list[KanbanTask]:
        """Update branch metadata for all active tasks across all boards (or a specific board) and append branch_switched event."""
        import datetime

        from sqlalchemy import select

        from app.database.models.kanban import KanbanTaskEventModel, KanbanTaskModel

        async with get_session() as session:
            stmt = select(KanbanTaskModel).where(
                KanbanTaskModel.status.in_([TaskStatus.BACKLOG, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.BLOCKED])
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
                    payload_json={"from": old_branch, "to": new_branch, "migrated": migrated},
                    created_at=datetime.datetime.now(datetime.UTC)
                )
                session.add(event)
            
            if tasks:
                await session.commit()
                for task in updated_tasks:
                    await session.refresh(task)
                from app.core.kanban.adapters.sqlalchemy_mapping import task_to_domain
                return [task_to_domain(t) for t in updated_tasks]
            return []

    async def get_board(self, board_id: str) -> KanbanBoard | None:
        async with get_session() as session:
            m = await session.get(KanbanBoardModel, board_id)
            return board_to_domain(m) if m else None

    async def list_boards(self) -> list[KanbanBoard]:
        async with get_session() as session:
            stmt = select(KanbanBoardModel).order_by(KanbanBoardModel.created_at.desc())
            result = await session.execute(stmt)
            return [board_to_domain(m) for m in result.scalars().all()]

    async def save_board(self, board: KanbanBoard) -> KanbanBoard:
        async with get_session() as session:
            existing = await session.get(KanbanBoardModel, board.board_id)
            if existing:
                apply_board_to_model(board, existing)
                await session.commit()
                await session.refresh(existing)
                return board_to_domain(existing)
            m = board_to_model(board)
            session.add(m)
            await session.commit()
            await session.refresh(m)
            return board_to_domain(m)

    async def delete_board(self, board_id: str) -> bool:
        async with get_session() as session:
            m = await session.get(KanbanBoardModel, board_id)
            if not m:
                return False
            await session.delete(m)
            await session.commit()
            return True

    # -- Task CRUD --

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
            stmt = (
                select(sqlfunc.count())
                .select_from(KanbanTaskModel)
                .where(KanbanTaskModel.board_id == board_id)
            )
            if status is not None:
                stmt = stmt.where(KanbanTaskModel.status == status.value)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def batch_task_stats(
        self, task_ids: list[str],
    ) -> dict[str, TaskCardStats]:
        """Batch-fetch per-task stats for card badges (avoids N+1).

        Four aggregate queries: parent edge count, child edge count,
        terminal-child count, user_comment event count.
        Only queries stats for the given task_ids (typically the current page).
        """
        if not task_ids:
            return {}

        async with get_session() as session:
            stats: dict[str, TaskCardStats] = {
                tid: TaskCardStats(0, 0, 0, 0) for tid in task_ids
            }

            dep_stmt = (
                select(
                    KanbanTaskEdgeModel.child_task_id,
                    sqlfunc.count().label("cnt"),
                )
                .where(KanbanTaskEdgeModel.child_task_id.in_(task_ids))
                .group_by(KanbanTaskEdgeModel.child_task_id)
            )
            dep_result = await session.execute(dep_stmt)
            dep_map: dict[str, int] = {
                row[0]: row[1] for row in dep_result.all()
            }

            child_total_stmt = (
                select(
                    KanbanTaskEdgeModel.parent_task_id,
                    sqlfunc.count().label("total"),
                )
                .where(KanbanTaskEdgeModel.parent_task_id.in_(task_ids))
                .group_by(KanbanTaskEdgeModel.parent_task_id)
            )
            child_total_result = await session.execute(child_total_stmt)
            child_map: dict[str, tuple[int, int]] = {
                row[0]: (row[1], 0) for row in child_total_result.all()
            }

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
                    KanbanTaskModel.status.in_(
                        [s.value for s in _TERMINAL_STATUSES]
                    ),
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
            comment_map: dict[str, int] = {
                row[0]: row[1] for row in comment_result.all()
            }

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
        self, board_id: str,
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
            stmt = (
                select(sqlfunc.min(KanbanTaskModel.updated_at))
                .where(
                    KanbanTaskModel.board_id == board_id,
                    KanbanTaskModel.status == TaskStatus.READY.value,
                )
            )
            row = await session.execute(stmt)
            oldest = row.scalar_one_or_none()
            if oldest is None:
                return None
            now = datetime.now(UTC)
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=UTC)
            return int((now - oldest).total_seconds())

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

    # -- Dependency edges (DAG) --

    async def _would_create_cycle(
        self, parent_id: str, child_id: str,
    ) -> bool:
        """DFS via parent chain to detect if adding edge would create a cycle."""
        if parent_id == child_id:
            return True
        async with get_session() as session:
            stmt = select(
                KanbanTaskEdgeModel.child_task_id,
                KanbanTaskEdgeModel.parent_task_id,
            )
            result = await session.execute(stmt)
            adj: dict[str, list[str]] = {}
            for c_id, p_id in result.all():
                adj.setdefault(c_id, []).append(p_id)

        visited: set[str] = set()
        stack = [parent_id]
        while stack:
            node = stack.pop()
            if node == child_id:
                return True
            if node in visited:
                continue
            visited.add(node)
            stack.extend(adj.get(node, []))
        return False

    async def add_edge(self, parent_task_id: str, child_task_id: str) -> TaskEdge:
        if await self._would_create_cycle(parent_task_id, child_task_id):
            raise ValueError(
                f"Adding edge {parent_task_id} -> {child_task_id} would create a cycle"
            )
        async with get_session() as session:
            existing = await session.execute(
                select(KanbanTaskEdgeModel).where(
                    KanbanTaskEdgeModel.parent_task_id == parent_task_id,
                    KanbanTaskEdgeModel.child_task_id == child_task_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                return TaskEdge(parent_task_id=parent_task_id, child_task_id=child_task_id)

            m = KanbanTaskEdgeModel(
                parent_task_id=parent_task_id,
                child_task_id=child_task_id,
            )
            session.add(m)
            await session.commit()
        return TaskEdge(parent_task_id=parent_task_id, child_task_id=child_task_id)

    async def remove_edge(self, parent_task_id: str, child_task_id: str) -> bool:
        async with get_session() as session:
            stmt = sql_delete(KanbanTaskEdgeModel).where(
                KanbanTaskEdgeModel.parent_task_id == parent_task_id,
                KanbanTaskEdgeModel.child_task_id == child_task_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return _exec_rowcount(result) > 0

    async def list_parents(self, task_id: str) -> list[str]:
        async with get_session() as session:
            stmt = select(KanbanTaskEdgeModel.parent_task_id).where(
                KanbanTaskEdgeModel.child_task_id == task_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_children(self, task_id: str) -> list[str]:
        async with get_session() as session:
            stmt = select(KanbanTaskEdgeModel.child_task_id).where(
                KanbanTaskEdgeModel.parent_task_id == task_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_board_edges(self, board_id: str) -> list[TaskEdge]:
        """Return all edges for tasks belonging to the given board."""
        async with get_session() as session:
            stmt = (
                select(
                    KanbanTaskEdgeModel.parent_task_id,
                    KanbanTaskEdgeModel.child_task_id,
                )
                .join(
                    KanbanTaskModel,
                    KanbanTaskEdgeModel.parent_task_id == KanbanTaskModel.id,
                )
                .where(KanbanTaskModel.board_id == board_id)
            )
            result = await session.execute(stmt)
            return [
                TaskEdge(parent_task_id=row[0], child_task_id=row[1])
                for row in result.all()
            ]

    async def are_dependencies_met(self, task_id: str) -> bool:
        async with get_session() as session:
            has_unmet = await session.execute(
                select(
                    exists().where(
                        KanbanTaskEdgeModel.child_task_id == task_id,
                        KanbanTaskEdgeModel.parent_task_id == KanbanTaskModel.id,
                        KanbanTaskModel.status.notin_(
                            [s.value for s in _TERMINAL_STATUSES]
                        ),
                    )
                )
            )
            return not has_unmet.scalar_one()

    # -- Agent reference cleanup (business-layer cascade, not in Protocol) --

    async def clear_agent_references(self, agent_id: str) -> int:
        """Set agent_id to NULL on all tasks referencing the given agent."""
        async with get_session() as session:
            stmt = (
                update(KanbanTaskModel)
                .where(KanbanTaskModel.agent_id == agent_id)
                .values(agent_id=None)
            )
            result = await session.execute(stmt)
            await session.commit()
            return _exec_rowcount(result)

    # -- Dispatch operations --

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

    # -- Heartbeat operations --

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

    async def list_zombie_tasks(
        self, board_id: str, timeout_seconds: int
    ) -> list[KanbanTask]:
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

    # -- Run history --

    async def create_run(self, task_id: str, worker_id: str) -> TaskRun:
        run_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC)
        async with get_session() as session:
            m = KanbanTaskRunModel(
                id=run_id,
                task_id=task_id,
                worker_id=worker_id,
                started_at=now,
            )
            session.add(m)
            await session.commit()
        return TaskRun(
            run_id=run_id,
            task_id=task_id,
            worker_id=worker_id,
            started_at=now,
        )

    async def complete_run(
        self,
        run_id: str,
        outcome: TaskRunOutcome,
        *,
        summary: str = "",
        error: str = "",
    ) -> TaskRun:
        now = datetime.now(UTC)
        async with get_session() as session:
            m = await session.get(KanbanTaskRunModel, run_id)
            if m is None:
                raise ValueError(f"Run {run_id} not found")
            m.outcome = outcome.value
            m.ended_at = now
            m.summary = summary
            m.error = error
            await session.commit()
            await session.refresh(m)
            return self._run_model_to_domain(m)

    async def list_runs(self, task_id: str) -> list[TaskRun]:
        async with get_session() as session:
            stmt = (
                select(KanbanTaskRunModel)
                .where(KanbanTaskRunModel.task_id == task_id)
                .order_by(KanbanTaskRunModel.started_at)
            )
            result = await session.execute(stmt)
            return [self._run_model_to_domain(m) for m in result.scalars().all()]

    # -- Event trail --

    async def append_event(
        self,
        task_id: str,
        kind: TaskEventKind,
        *,
        payload: dict[str, object] | None = None,
        run_id: str | None = None,
    ) -> TaskEvent:
        async with get_session() as session:
            m = KanbanTaskEventModel(
                task_id=task_id,
                kind=kind.value,
                payload_json=payload,
                run_id=run_id,
            )
            session.add(m)
            await session.commit()
            await session.refresh(m)
            return self._event_model_to_domain(m)

    async def list_events(
        self, task_id: str, *, since_id: int | None = None,
    ) -> list[TaskEvent]:
        async with get_session() as session:
            stmt = (
                select(KanbanTaskEventModel)
                .where(KanbanTaskEventModel.task_id == task_id)
            )
            if since_id is not None:
                stmt = stmt.where(KanbanTaskEventModel.id > since_id)
            stmt = stmt.order_by(KanbanTaskEventModel.id)
            result = await session.execute(stmt)
            return [self._event_model_to_domain(m) for m in result.scalars().all()]

    async def list_board_events(
        self,
        board_id: str,
        *,
        kinds: list[str] | None = None,
        assignee: str | None = None,
        since_id: int | None = None,
        since_time: datetime | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Return board-level events with task metadata (title, assignee).

        JOIN kanban_task_events + kanban_tasks for board-scoped aggregation.
        Returns dicts with event fields + task_title + task_assignee.
        """
        async with get_session() as session:
            stmt = (
                select(
                    KanbanTaskEventModel.id,
                    KanbanTaskEventModel.task_id,
                    KanbanTaskEventModel.kind,
                    KanbanTaskEventModel.payload_json,
                    KanbanTaskEventModel.run_id,
                    KanbanTaskEventModel.created_at,
                    KanbanTaskModel.title.label("task_title"),
                    KanbanTaskModel.agent_id.label("task_assignee"),
                )
                .join(KanbanTaskModel, KanbanTaskModel.id == KanbanTaskEventModel.task_id)
                .where(KanbanTaskModel.board_id == board_id)
            )
            if kinds:
                stmt = stmt.where(KanbanTaskEventModel.kind.in_(kinds))
            if assignee:
                stmt = stmt.where(KanbanTaskModel.agent_id == assignee)
            if since_id is not None:
                stmt = stmt.where(KanbanTaskEventModel.id > since_id)
            if since_time is not None:
                stmt = stmt.where(KanbanTaskEventModel.created_at >= since_time)
            stmt = stmt.order_by(KanbanTaskEventModel.id.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.all()
            return [
                {
                    "event_id": r.id,
                    "task_id": r.task_id,
                    "task_title": r.task_title or "",
                    "task_assignee": r.task_assignee or "",
                    "kind": r.kind,
                    "payload": r.payload_json,
                    "run_id": r.run_id,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]

    # -- Internal mapping helpers --

    @staticmethod
    def _run_model_to_domain(m: KanbanTaskRunModel) -> TaskRun:
        return TaskRun(
            run_id=m.id,
            task_id=m.task_id,
            worker_id=m.worker_id,
            started_at=m.started_at,
            ended_at=m.ended_at,
            outcome=TaskRunOutcome(m.outcome) if m.outcome else None,
            summary=m.summary or "",
            error=m.error or "",
            metadata=m.metadata_json or {},
        )

    @staticmethod
    def _event_model_to_domain(m: KanbanTaskEventModel) -> TaskEvent:
        return TaskEvent(
            event_id=m.id,
            task_id=m.task_id,
            kind=TaskEventKind(m.kind),
            payload=m.payload_json,
            run_id=m.run_id,
            created_at=m.created_at,
        )
