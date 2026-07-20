"""SQLAlchemy implementation of the CronStore protocol.

CRUD operations for jobs, run records, and monitor state.
ORM mapping is delegated to ``sqlalchemy_mapping``;
usage aggregation lives in ``sqlalchemy_aggregation``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from myrm_agent_harness.infra.incremental.types import MonitorState
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronRunRecord,
    JobStatus,
)
from sqlalchemy import delete, select, update
from sqlalchemy.sql import func as sqlfunc

from app.core.cron.adapters.sqlalchemy_aggregation import UsageAggregateResult, aggregate_usage
from app.core.cron.adapters.sqlalchemy_mapping import (
    apply_job_to_model,
    job_to_domain,
    job_to_model,
    row_to_monitor_state,
    run_to_domain,
)
from app.database.connection import get_session
from app.database.models import CronJobModel, CronRunModel, MonitorStateModel


def _exec_rowcount(result: object) -> int:
    rc = getattr(result, "rowcount", None)
    return rc if isinstance(rc, int) else 0


class SqlAlchemyCronStore:
    """CronStore backed by SQLAlchemy + app.database models."""

    # ------------------------------------------------------------------
    # Job CRUD
    # ------------------------------------------------------------------

    async def list_jobs(
        self,
        *,
        user_id: str | None = None,
        name_filter: str | None = None,
        chat_id: str | None = None,
        due_before: datetime | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CronJob]:
        stmt = select(CronJobModel)

        if user_id is not None:
            stmt = stmt.where(CronJobModel.user_id == user_id)

        if chat_id is not None:
            stmt = stmt.where(CronJobModel.chat_id == chat_id)

        if name_filter:
            stmt = stmt.where(CronJobModel.name.ilike(f"%{name_filter}%"))

        if due_before is not None:
            stmt = stmt.where(
                CronJobModel.status == JobStatus.ACTIVE,
                CronJobModel.next_run_at.isnot(None),
                CronJobModel.next_run_at <= due_before,
            )
        else:
            stmt = stmt.order_by(CronJobModel.created_at.desc())

        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        async with get_session() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [job_to_domain(r) for r in rows]

    async def count_jobs(self, *, user_id: str | None = None) -> int:
        stmt = select(sqlfunc.count()).select_from(CronJobModel)
        if user_id is not None:
            stmt = stmt
        async with get_session() as session:
            return (await session.execute(stmt)).scalar_one()

    async def get_job(self, job_id: str) -> CronJob | None:
        async with get_session() as session:
            row = (await session.execute(select(CronJobModel).where(CronJobModel.id == job_id))).scalar_one_or_none()
            return job_to_domain(row) if row else None

    async def earliest_next_run(self) -> datetime | None:
        async with get_session() as session:
            result = await session.execute(
                select(sqlfunc.min(CronJobModel.next_run_at)).where(
                    CronJobModel.status == JobStatus.ACTIVE,
                    CronJobModel.next_run_at.isnot(None),
                )
            )
            row = result.scalar()
            if row and row.tzinfo is None:
                return row.replace(tzinfo=timezone.utc)
            return row

    async def save_job(self, job: CronJob) -> CronJob:
        async with get_session() as session:
            existing = (await session.execute(select(CronJobModel).where(CronJobModel.id == job.id))).scalar_one_or_none()

            if existing:
                apply_job_to_model(existing, job)
                await session.commit()
                await session.refresh(existing)
                return job_to_domain(existing)

            model_obj = job_to_model(job)
            session.add(model_obj)
            await session.commit()
            await session.refresh(model_obj)
            return job_to_domain(model_obj)

    async def delete_job(self, job_id: str) -> bool:
        async with get_session() as session:
            result = await session.execute(delete(CronJobModel).where(CronJobModel.id == job_id))
            await session.commit()
            return _exec_rowcount(result) > 0

    async def claim_due(self, job_ids: list[str]) -> None:
        async with get_session() as session:
            await session.execute(update(CronJobModel).where(CronJobModel.id.in_(job_ids)).values(next_run_at=None))
            await session.commit()

    # ------------------------------------------------------------------
    # Run records
    # ------------------------------------------------------------------

    async def save_run(self, run: CronRunRecord) -> None:
        async with get_session() as session:
            session.add(
                CronRunModel(
                    id=run.id,
                    job_id=run.job_id,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    duration_ms=run.duration_ms,
                    status=run.status,
                    output=run.output,
                    error=run.error,
                    model=run.model,
                    usage_input_tokens=run.usage_input_tokens,
                    usage_output_tokens=run.usage_output_tokens,
                    usage_total_tokens=run.usage_total_tokens,
                    trigger_source=run.trigger_source,
                    delivery_status=run.delivery_status,
                    delivery_error=run.delivery_error,
                    metadata_json=run.metadata,
                    integrity_hash=run.integrity_hash or None,
                    prev_hash=run.prev_hash or None,
                )
            )
            await session.commit()

    async def get_latest_integrity_hash(self, job_id: str) -> str | None:
        async with get_session() as session:
            stmt = (
                select(CronRunModel.integrity_hash)
                .where(CronRunModel.job_id == job_id)
                .where(CronRunModel.integrity_hash.isnot(None))
                .order_by(CronRunModel.started_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_runs(
        self,
        job_id: str | None = None,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> list[CronRunRecord]:
        async with get_session() as session:
            stmt = select(CronRunModel)
            if job_id is not None:
                stmt = stmt.where(CronRunModel.job_id == job_id)
            if status:
                stmt = stmt.where(CronRunModel.status == status)
            stmt = stmt.order_by(CronRunModel.started_at.desc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return [run_to_domain(r) for r in result.scalars().all()]

    async def count_runs(
        self,
        job_id: str | None = None,
        *,
        status: str | None = None,
    ) -> int:
        async with get_session() as session:
            stmt = select(sqlfunc.count()).select_from(CronRunModel)
            if job_id is not None:
                stmt = stmt.where(CronRunModel.job_id == job_id)
            if status:
                stmt = stmt.where(CronRunModel.status == status)
            return (await session.execute(stmt)).scalar() or 0

    async def list_orphaned_active(self) -> list[CronJob]:
        stmt = select(CronJobModel).where(
            CronJobModel.status == JobStatus.ACTIVE,
            CronJobModel.next_run_at.is_(None),
        )
        async with get_session() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [job_to_domain(r) for r in rows]

    async def purge_old_runs(self, before: datetime) -> int:
        async with get_session() as session:
            result = await session.execute(delete(CronRunModel).where(CronRunModel.finished_at < before))
            await session.commit()
            return _exec_rowcount(result)

    async def delete_job_cascade(self, job_id: str) -> bool:
        async with get_session() as session:
            await session.execute(delete(MonitorStateModel).where(MonitorStateModel.job_id == job_id))
            await session.execute(delete(CronRunModel).where(CronRunModel.job_id == job_id))
            result = await session.execute(delete(CronJobModel).where(CronJobModel.id == job_id))
            await session.commit()
            return _exec_rowcount(result) > 0

    # ------------------------------------------------------------------
    # Monitor state
    # ------------------------------------------------------------------

    async def get_monitor_state(self, job_id: str) -> MonitorState | None:
        async with get_session() as session:
            row = (
                await session.execute(select(MonitorStateModel).where(MonitorStateModel.job_id == job_id))
            ).scalar_one_or_none()

            if not row:
                return None

            return row_to_monitor_state(row)

    async def save_monitor_state(self, state: MonitorState) -> None:
        async with get_session() as session:
            existing = (
                await session.execute(select(MonitorStateModel).where(MonitorStateModel.job_id == state.job_id))
            ).scalar_one_or_none()

            if existing:
                existing.monitor_type = state.monitor_type
                existing.data = state.data
                existing.ttl_days = state.ttl_days
                existing.updated_at = state.updated_at
                existing.failure_count = state.failure_count
                existing.last_failure_at = state.last_failure_at
                existing.last_reset_at = state.last_reset_at
                existing.last_reset_reason = state.last_reset_reason
            else:
                model_obj = MonitorStateModel(
                    job_id=state.job_id,
                    monitor_type=state.monitor_type,
                    data=state.data,
                    ttl_days=state.ttl_days,
                    updated_at=state.updated_at,
                    failure_count=state.failure_count,
                    last_failure_at=state.last_failure_at,
                    last_reset_at=state.last_reset_at,
                    last_reset_reason=state.last_reset_reason,
                )
                session.add(model_obj)

            await session.commit()

    async def batch_get_monitor_states(self, job_ids: list[str]) -> dict[str, MonitorState]:
        if not job_ids:
            return {}

        async with get_session() as session:
            rows = (await session.execute(select(MonitorStateModel).where(MonitorStateModel.job_id.in_(job_ids)))).scalars().all()

            return {row.job_id: row_to_monitor_state(row) for row in rows}

    async def delete_monitor_state(self, job_id: str) -> bool:
        async with get_session() as session:
            result = await session.execute(delete(MonitorStateModel).where(MonitorStateModel.job_id == job_id))
            await session.commit()
            return _exec_rowcount(result) > 0

    # ------------------------------------------------------------------
    # Usage aggregation (delegates to sqlalchemy_aggregation module)
    # ------------------------------------------------------------------

    async def aggregate_usage(
        self,
        user_id: str,
        *,
        days: int | None = 7,
    ) -> UsageAggregateResult:
        return await aggregate_usage(user_id, days=days)
