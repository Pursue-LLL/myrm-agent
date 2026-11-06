"""[INPUT]
- .common (POS: shared types and helpers)

[OUTPUT]
- RunsMixin

[POS]
SqlAlchemyKanbanStore mixin: task run rows (create/complete/list) and run model conversion.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.kanban.types import (
    TaskRun,
    TaskRunOutcome,
)
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanTaskRunModel,
)


class RunsMixin:
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
        token_usage: dict[str, int] | None = None,
        cost_usd: float | None = None,
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
            if token_usage is not None:
                m.token_usage_json = token_usage
            if cost_usd is not None:
                m.cost_usd = cost_usd
            await session.commit()
            await session.refresh(m)
            return self._run_model_to_domain(m)

    async def list_runs(self, task_id: str) -> list[TaskRun]:
        async with get_session() as session:
            stmt = select(KanbanTaskRunModel).where(KanbanTaskRunModel.task_id == task_id).order_by(KanbanTaskRunModel.started_at)
            result = await session.execute(stmt)
            return [self._run_model_to_domain(m) for m in result.scalars().all()]

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
            token_usage=m.token_usage_json,
            cost_usd=m.cost_usd,
        )
