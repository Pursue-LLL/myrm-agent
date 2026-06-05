"""SQLAlchemy implementation of the CommitmentStore protocol.

[INPUT]
- myrm_agent_harness.toolkits.commitment::{CommitmentRecord, CommitmentStatus, CommitmentDueWindow, is_active_status}
- app.database.models::CommitmentModel
- app.database.connection::get_session

[OUTPUT]
- SqlAlchemyCommitmentStore: Concrete CommitmentStore backed by SQLAlchemy.

[POS]
Server-layer SQLite commitment store. Implements the Harness-defined
CommitmentStore protocol using SQLAlchemy ORM operations.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.commitment.types import (
    CommitmentDueWindow,
    CommitmentRecord,
    CommitmentStatus,
)
from sqlalchemy import select, update

from app.database.connection import get_session
from app.database.models import CommitmentModel

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = (CommitmentStatus.PENDING.value, CommitmentStatus.SNOOZED.value)


def _to_domain(row: CommitmentModel) -> CommitmentRecord:
    """Convert ORM model to domain record."""
    from myrm_agent_harness.toolkits.commitment.types import (
        CommitmentKind,
        CommitmentSensitivity,
    )

    return CommitmentRecord(
        id=row.id,
        agent_id=row.agent_id,
        user_id=row.user_id,
        channel=row.channel,
        kind=CommitmentKind(row.kind),
        sensitivity=CommitmentSensitivity(row.sensitivity),
        status=CommitmentStatus(row.status),
        reason=row.reason,
        suggested_text=row.suggested_text,
        dedupe_key=row.dedupe_key,
        confidence=row.confidence,
        due_window=CommitmentDueWindow(
            earliest_ms=row.due_earliest_ms,
            latest_ms=row.due_latest_ms,
            timezone=row.due_timezone,
        ),
        source_chat_id=row.source_chat_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        attempts=row.attempts,
        last_attempt_at=row.last_attempt_at,
        sent_at=row.sent_at,
        dismissed_at=row.dismissed_at,
        snoozed_until_ms=row.snoozed_until_ms,
        expired_at=row.expired_at,
    )


def _to_model(record: CommitmentRecord) -> CommitmentModel:
    """Convert domain record to ORM model."""
    return CommitmentModel(
        id=record.id,
        agent_id=record.agent_id,
        user_id=record.user_id,
        channel=record.channel,
        kind=record.kind.value,
        sensitivity=record.sensitivity.value,
        status=record.status.value,
        reason=record.reason,
        suggested_text=record.suggested_text,
        dedupe_key=record.dedupe_key,
        confidence=record.confidence,
        due_earliest_ms=record.due_window.earliest_ms,
        due_latest_ms=record.due_window.latest_ms,
        due_timezone=record.due_window.timezone,
        source_chat_id=record.source_chat_id,
        attempts=record.attempts,
    )


class SqlAlchemyCommitmentStore:
    """CommitmentStore backed by SQLAlchemy + SQLite/PostgreSQL."""

    async def upsert(self, record: CommitmentRecord) -> CommitmentRecord:
        """Insert or update by dedupe_key within (agent_id, user_id, channel) scope."""
        async with get_session() as session:
            existing = (
                (
                    await session.execute(
                        select(CommitmentModel).where(
                            CommitmentModel.agent_id == record.agent_id,
                            CommitmentModel.user_id == record.user_id,
                            CommitmentModel.channel == record.channel,
                            CommitmentModel.dedupe_key == record.dedupe_key,
                            CommitmentModel.status.in_(_ACTIVE_STATUSES),
                        )
                    )
                )
                .scalars()
                .first()
            )

            if existing is not None:
                existing.reason = record.reason or existing.reason
                existing.suggested_text = record.suggested_text or existing.suggested_text
                existing.confidence = max(existing.confidence, record.confidence)
                existing.due_earliest_ms = min(existing.due_earliest_ms, record.due_window.earliest_ms)
                existing.due_latest_ms = max(existing.due_latest_ms, record.due_window.latest_ms)
                existing.due_timezone = record.due_window.timezone
                await session.commit()
                await session.refresh(existing)
                return _to_domain(existing)

            model = _to_model(record)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _to_domain(model)

    async def list_pending(
        self,
        *,
        agent_id: str,
        user_id: str,
        now_ms: int,
        limit: int = 20,
    ) -> list[CommitmentRecord]:
        """List active commitments (pending + unsnoozed)."""
        async with get_session() as session:
            stmt = (
                select(CommitmentModel)
                .where(
                    CommitmentModel.agent_id == agent_id,
                    CommitmentModel.user_id == user_id,
                    CommitmentModel.status.in_(_ACTIVE_STATUSES),
                )
                .order_by(CommitmentModel.due_earliest_ms.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                _to_domain(r)
                for r in rows
                if r.status == CommitmentStatus.PENDING.value or (r.snoozed_until_ms is not None and r.snoozed_until_ms <= now_ms)
            ]

    async def list_due(
        self,
        *,
        agent_id: str,
        user_id: str,
        now_ms: int,
        limit: int = 3,
    ) -> list[CommitmentRecord]:
        """List commitments whose due window has arrived."""
        async with get_session() as session:
            stmt = (
                select(CommitmentModel)
                .where(
                    CommitmentModel.agent_id == agent_id,
                    CommitmentModel.user_id == user_id,
                    CommitmentModel.status.in_(_ACTIVE_STATUSES),
                    CommitmentModel.due_earliest_ms <= now_ms,
                )
                .order_by(CommitmentModel.due_earliest_ms.asc())
                .limit(limit * 2)
            )
            rows = (await session.execute(stmt)).scalars().all()

            due: list[CommitmentRecord] = []
            for r in rows:
                if r.status == CommitmentStatus.SNOOZED.value:
                    if r.snoozed_until_ms is not None and r.snoozed_until_ms > now_ms:
                        continue
                due.append(_to_domain(r))
                if len(due) >= limit:
                    break
            return due

    async def mark_status(
        self,
        ids: list[str],
        status: CommitmentStatus,
        now_ms: int,
    ) -> int:
        """Transition commitments to a terminal status."""
        if not ids:
            return 0

        now_dt = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
        values: dict[str, object] = {
            "status": status.value,
            "updated_at": now_dt,
        }
        if status == CommitmentStatus.SENT:
            values["sent_at"] = now_dt
        elif status == CommitmentStatus.DISMISSED:
            values["dismissed_at"] = now_dt
        elif status == CommitmentStatus.EXPIRED:
            values["expired_at"] = now_dt

        async with get_session() as session:
            result = await session.execute(
                update(CommitmentModel)
                .where(
                    CommitmentModel.id.in_(ids),
                    CommitmentModel.status.in_(_ACTIVE_STATUSES),
                )
                .values(**values)
            )
            await session.commit()
            rc = getattr(result, "rowcount", 0)
            return rc if isinstance(rc, int) else 0

    async def mark_attempted(self, ids: list[str], now_ms: int) -> int:
        """Increment attempt counter."""
        if not ids:
            return 0

        now_dt = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
        async with get_session() as session:
            result = await session.execute(
                update(CommitmentModel)
                .where(CommitmentModel.id.in_(ids))
                .values(
                    attempts=CommitmentModel.attempts + 1,
                    last_attempt_at=now_dt,
                    updated_at=now_dt,
                )
            )
            await session.commit()
            rc = getattr(result, "rowcount", 0)
            return rc if isinstance(rc, int) else 0

    async def snooze(self, commitment_id: str, until_ms: int, now_ms: int) -> bool:
        """Snooze a commitment until a future time."""
        now_dt = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
        async with get_session() as session:
            result = await session.execute(
                update(CommitmentModel)
                .where(
                    CommitmentModel.id == commitment_id,
                    CommitmentModel.status.in_(_ACTIVE_STATUSES),
                )
                .values(
                    status=CommitmentStatus.SNOOZED.value,
                    snoozed_until_ms=until_ms,
                    updated_at=now_dt,
                )
            )
            await session.commit()
            rc = getattr(result, "rowcount", 0)
            return (rc if isinstance(rc, int) else 0) > 0

    async def count_sent_rolling(
        self,
        *,
        agent_id: str,
        user_id: str,
        since_ms: int,
    ) -> int:
        """Count commitments sent within a rolling window."""
        since_dt = datetime.fromtimestamp(since_ms / 1000, tz=UTC)
        async with get_session() as session:
            from sqlalchemy import func as sqlfunc

            result = await session.execute(
                select(sqlfunc.count())
                .select_from(CommitmentModel)
                .where(
                    CommitmentModel.agent_id == agent_id,
                    CommitmentModel.user_id == user_id,
                    CommitmentModel.status == CommitmentStatus.SENT.value,
                    CommitmentModel.sent_at >= since_dt,
                )
            )
            return result.scalar() or 0

    async def expire_stale(self, now_ms: int, expire_after_ms: int) -> int:
        """Expire commitments past their latest + grace period."""
        cutoff_ms = now_ms - expire_after_ms
        now_dt = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
        async with get_session() as session:
            result = await session.execute(
                update(CommitmentModel)
                .where(
                    CommitmentModel.status.in_(_ACTIVE_STATUSES),
                    CommitmentModel.due_latest_ms < cutoff_ms,
                )
                .values(
                    status=CommitmentStatus.EXPIRED.value,
                    expired_at=now_dt,
                    updated_at=now_dt,
                )
            )
            await session.commit()
            rc = getattr(result, "rowcount", 0)
            return rc if isinstance(rc, int) else 0

    async def list_all(
        self,
        *,
        user_id: str,
        status: CommitmentStatus | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[CommitmentRecord]:
        """List all commitments for a user with optional filters."""
        async with get_session() as session:
            stmt = select(CommitmentModel).where(
                CommitmentModel.user_id == user_id,
            )
            if status is not None:
                stmt = stmt.where(CommitmentModel.status == status.value)
            if agent_id is not None:
                stmt = stmt.where(CommitmentModel.agent_id == agent_id)

            stmt = stmt.order_by(CommitmentModel.due_earliest_ms.asc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(r) for r in rows]
