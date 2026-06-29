"""Tests for SqlAlchemyCommitmentStore CRUD and lifecycle operations."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from myrm_agent_harness.toolkits.memory.proactive.types import (
    CommitmentDueWindow,
    CommitmentKind,
    CommitmentRecord,
    CommitmentSensitivity,
    CommitmentStatus,
)


def _record(
    *,
    record_id: str,
    agent_id: str,
    user_id: str = "default",
    dedupe_key: str | None = None,
    earliest_ms: int,
    latest_ms: int,
    status: CommitmentStatus = CommitmentStatus.PENDING,
) -> CommitmentRecord:
    return CommitmentRecord(
        id=record_id,
        agent_id=agent_id,
        user_id=user_id,
        channel="web",
        kind=CommitmentKind.OPEN_LOOP,
        sensitivity=CommitmentSensitivity.ROUTINE,
        status=status,
        reason="test reason",
        suggested_text="follow up text",
        dedupe_key=dedupe_key or record_id,
        confidence=0.8,
        due_window=CommitmentDueWindow(
            earliest_ms=earliest_ms,
            latest_ms=latest_ms,
            timezone="UTC",
        ),
    )


@pytest.mark.asyncio
async def test_upsert_insert_and_update_by_dedupe_key() -> None:
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    agent_id = "store-upsert-agent"
    store = SqlAlchemyCommitmentStore()

    inserted = await store.upsert(
        _record(record_id="cm_ins", agent_id=agent_id, dedupe_key="dup-1", earliest_ms=now_ms, latest_ms=now_ms + 3600_000)
    )
    assert inserted.dedupe_key == "dup-1"

    updated = await store.upsert(
        _record(
            record_id="cm_ins2",
            agent_id=agent_id,
            dedupe_key="dup-1",
            earliest_ms=now_ms - 1000,
            latest_ms=now_ms + 7200_000,
        ).model_copy(update={"confidence": 0.95, "suggested_text": "updated text"})
    )
    assert updated.id == inserted.id
    assert updated.confidence == 0.95
    assert updated.suggested_text == "updated text"


@pytest.mark.asyncio
async def test_list_pending_respects_snooze_window() -> None:
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore, _to_model
    from app.database.connection import get_session

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    agent_id = "store-pending-agent"
    store = SqlAlchemyCommitmentStore()

    pending = _record(record_id="cm_pend", agent_id=agent_id, earliest_ms=now_ms, latest_ms=now_ms + 3600_000)
    snoozed = _record(record_id="cm_snz", agent_id=agent_id, earliest_ms=now_ms, latest_ms=now_ms + 3600_000)
    snoozed.status = CommitmentStatus.SNOOZED
    snoozed.snoozed_until_ms = now_ms + 3600_000

    async with get_session() as session:
        session.add(_to_model(pending))
        session.add(_to_model(snoozed))
        await session.commit()

    active = await store.list_pending(agent_id=agent_id, user_id="default", now_ms=now_ms, limit=10)
    assert {item.id for item in active} == {"cm_pend"}


@pytest.mark.asyncio
async def test_mark_status_dismissed_and_expire_stale_scoped() -> None:
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore, _to_model
    from app.database.connection import get_session

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    expire_after_ms = 72 * 3600 * 1000
    agent_id = "store-expire-agent"
    store = SqlAlchemyCommitmentStore()

    stale = _record(
        record_id="cm_stale",
        agent_id=agent_id,
        earliest_ms=now_ms - expire_after_ms - 10_000,
        latest_ms=now_ms - expire_after_ms - 5000,
    )
    fresh = _record(record_id="cm_fresh", agent_id=agent_id, earliest_ms=now_ms, latest_ms=now_ms + 3600_000)

    async with get_session() as session:
        session.add(_to_model(stale))
        session.add(_to_model(fresh))
        await session.commit()

    expired_count = await store.expire_stale(
        now_ms,
        expire_after_ms,
        agent_id=agent_id,
        user_id="default",
    )
    assert expired_count == 1

    dismissed = await store.mark_status(["cm_fresh"], CommitmentStatus.DISMISSED, now_ms)
    assert dismissed == 1

    items = await store.list_all(user_id="default", agent_id=agent_id, status=CommitmentStatus.DISMISSED)
    assert len(items) == 1
    assert items[0].id == "cm_fresh"


@pytest.mark.asyncio
async def test_count_sent_rolling_and_mark_attempted() -> None:
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore, _to_model
    from app.database.connection import get_session

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    agent_id = "store-sent-agent"
    store = SqlAlchemyCommitmentStore()

    sent = _record(record_id="cm_sent_roll", agent_id=agent_id, earliest_ms=now_ms, latest_ms=now_ms + 3600_000)
    pending = _record(record_id="cm_att", agent_id=agent_id, earliest_ms=now_ms, latest_ms=now_ms + 3600_000)

    async with get_session() as session:
        session.add(_to_model(sent))
        session.add(_to_model(pending))
        await session.commit()

    await store.mark_status(["cm_sent_roll"], CommitmentStatus.SENT, now_ms)
    assert await store.count_sent_rolling(agent_id=agent_id, user_id="default", since_ms=now_ms - 3600_000) == 1

    assert await store.mark_attempted([], now_ms) == 0
    attempted = await store.mark_attempted(["cm_att"], now_ms)
    assert attempted == 1

    rows = await store.list_all(user_id="default", agent_id=agent_id)
    by_id = {row.id: row for row in rows}
    assert by_id["cm_att"].attempts == 1


@pytest.mark.asyncio
async def test_snooze_returns_false_for_missing_id() -> None:
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    store = SqlAlchemyCommitmentStore()
    assert await store.snooze("missing-id", now_ms + 3600_000, now_ms) is False
