"""In-flight run markers of the SQLAlchemy cron store.

[INPUT]
- app.core.cron.adapters.sqlalchemy_mapping::as_utc (POS: ORM <-> Domain mapping and the UTC rule for stored timestamps)
- app.database.connection::get_session (POS: async database session)
- app.database.models::CronInflightModel (POS: marker of a job whose run is in flight)

[OUTPUT]
- SqlAlchemyInflightMixin: `mark_running`, `clear_running` and `list_running` of the CronStore protocol

[POS]
Mixed into ``SqlAlchemyCronStore``. Each method is one statement that writes first in its transaction, so none needs
``acquire_write_lock``. The table has one row per job and is empty whenever no run is in flight.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.cron.adapters.sqlalchemy_mapping import as_utc
from app.database.connection import get_session
from app.database.models import CronInflightModel


class SqlAlchemyInflightMixin:
    """The in-flight markers of ``SqlAlchemyCronStore``."""

    async def mark_running(self, job_id: str) -> None:
        now = datetime.now(timezone.utc)
        upsert = (
            sqlite_insert(CronInflightModel)
            .values(job_id=job_id, started_at=now)
            .on_conflict_do_update(index_elements=[CronInflightModel.job_id], set_={"started_at": now})
        )
        async with get_session() as session:
            await session.execute(upsert)
            await session.commit()

    async def clear_running(self, job_id: str) -> None:
        async with get_session() as session:
            await session.execute(delete(CronInflightModel).where(CronInflightModel.job_id == job_id))
            await session.commit()

    async def list_running(self) -> list[tuple[str, datetime]]:
        stmt = select(CronInflightModel.job_id, CronInflightModel.started_at).order_by(
            CronInflightModel.started_at, CronInflightModel.job_id
        )
        async with get_session() as session:
            rows = (await session.execute(stmt)).all()
        return [(row.job_id, as_utc(row.started_at)) for row in rows]
