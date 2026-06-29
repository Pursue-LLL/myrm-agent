"""Tests for SqlAlchemyCommitmentStore list_due stale window filtering."""

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


def _record(*, record_id: str, latest_ms: int) -> CommitmentRecord:
    return CommitmentRecord(
        id=record_id,
        agent_id="agent-1",
        user_id="default",
        channel="web",
        kind=CommitmentKind.OPEN_LOOP,
        sensitivity=CommitmentSensitivity.ROUTINE,
        status=CommitmentStatus.PENDING,
        reason="test",
        suggested_text="follow up",
        dedupe_key=record_id,
        confidence=0.8,
        due_window=CommitmentDueWindow(
            earliest_ms=latest_ms - 1000,
            latest_ms=latest_ms,
            timezone="UTC",
        ),
    )


@pytest.mark.asyncio
async def test_list_due_skips_stale_commitments() -> None:
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore, _to_model
    from app.database.connection import get_session

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    expire_after_ms = 72 * 3600 * 1000

    fresh = _record(record_id="fresh", latest_ms=now_ms)
    stale = _record(record_id="stale", latest_ms=now_ms - expire_after_ms - 1)

    store = SqlAlchemyCommitmentStore()

    async with get_session() as session:
        session.add(_to_model(fresh))
        session.add(_to_model(stale))
        await session.commit()

    due = await store.list_due(
        agent_id="agent-1",
        user_id="default",
        now_ms=now_ms,
        limit=5,
        expire_after_ms=expire_after_ms,
    )

    assert [item.id for item in due] == ["fresh"]
