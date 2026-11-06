"""[INPUT]
- .common (POS: shared types and helpers)

[OUTPUT]
- EventsMixin

[POS]
SqlAlchemyKanbanStore mixin: task/board event log writes and reads.
"""

from __future__ import annotations

from datetime import datetime

from myrm_agent_harness.toolkits.kanban.types import (
    TaskEvent,
    TaskEventKind,
)
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanTaskEventModel,
    KanbanTaskModel,
)

from .common import (
    BoardEventRow,
)


class EventsMixin:
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
        self,
        task_id: str,
        *,
        since_id: int | None = None,
    ) -> list[TaskEvent]:
        async with get_session() as session:
            stmt = select(KanbanTaskEventModel).where(KanbanTaskEventModel.task_id == task_id)
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
    ) -> list[BoardEventRow]:
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
