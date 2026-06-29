"""Tests for follow-up delivery ack and failed-delivery snooze."""

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


def _record(*, record_id: str, now_ms: int) -> CommitmentRecord:
    return CommitmentRecord(
        id=record_id,
        agent_id="agent-1",
        user_id="default",
        channel="web",
        kind=CommitmentKind.EVENT_CHECK_IN,
        sensitivity=CommitmentSensitivity.ROUTINE,
        status=CommitmentStatus.PENDING,
        reason="interview prep",
        suggested_text="How is interview prep going?",
        dedupe_key=record_id,
        confidence=0.85,
        due_window=CommitmentDueWindow(
            earliest_ms=now_ms - 1000,
            latest_ms=now_ms + 3600_000,
            timezone="UTC",
        ),
    )


@pytest.mark.asyncio
async def test_confirm_delivery_marks_sent() -> None:
    from app.core.memory.proactive.delivery_tracker import (
        confirm_follow_up_delivery,
        register_follow_up_attempts,
        reset_follow_up_delivery,
    )
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore, _to_model
    from app.database.connection import get_session

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    record = _record(record_id="cm_sent", now_ms=now_ms)

    async with get_session() as session:
        session.add(_to_model(record))
        await session.commit()

    reset_follow_up_delivery()
    register_follow_up_attempts(["cm_sent"])
    await confirm_follow_up_delivery(delivered=True)

    store = SqlAlchemyCommitmentStore()
    items = await store.list_all(user_id="default", agent_id="agent-1", limit=10)
    sent = next(item for item in items if item.id == "cm_sent")
    assert sent.status == CommitmentStatus.SENT


@pytest.mark.asyncio
async def test_failed_delivery_snoozes_and_list_due_skips_until_window() -> None:
    from app.core.memory.proactive.delivery_tracker import (
        FAILED_DELIVERY_SNOOZE_MS,
        confirm_follow_up_delivery,
        register_follow_up_attempts,
        reset_follow_up_delivery,
    )
    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore, _to_model
    from app.database.connection import get_session

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    record = _record(record_id="cm_snooze", now_ms=now_ms)

    async with get_session() as session:
        session.add(_to_model(record))
        await session.commit()

    reset_follow_up_delivery()
    register_follow_up_attempts(["cm_snooze"])
    await confirm_follow_up_delivery(delivered=False)

    store = SqlAlchemyCommitmentStore()
    items = await store.list_all(user_id="default", agent_id="agent-1", limit=10)
    snoozed = next(item for item in items if item.id == "cm_snooze")
    assert snoozed.status == CommitmentStatus.SNOOZED
    assert snoozed.snoozed_until_ms is not None
    snooze_delta = snoozed.snoozed_until_ms - now_ms
    assert FAILED_DELIVERY_SNOOZE_MS <= snooze_delta <= FAILED_DELIVERY_SNOOZE_MS + 5000

    due_during_snooze = await store.list_due(
        agent_id="agent-1",
        user_id="default",
        now_ms=snoozed.snoozed_until_ms - 1_000,
        limit=5,
    )
    assert due_during_snooze == []

    due_after_snooze = await store.list_due(
        agent_id="agent-1",
        user_id="default",
        now_ms=snoozed.snoozed_until_ms + 1,
        limit=5,
    )
    assert [item.id for item in due_after_snooze] == ["cm_snooze"]


@pytest.mark.asyncio
async def test_confirm_delivery_no_registered_ids() -> None:
    from app.core.memory.proactive.delivery_tracker import (
        confirm_follow_up_delivery,
        reset_follow_up_delivery,
    )

    reset_follow_up_delivery()
    await confirm_follow_up_delivery(delivered=False)


@pytest.mark.asyncio
async def test_failed_snooze_logs_when_record_missing() -> None:
    from app.core.memory.proactive.delivery_tracker import (
        confirm_follow_up_delivery,
        register_follow_up_attempts,
        reset_follow_up_delivery,
    )

    reset_follow_up_delivery()
    register_follow_up_attempts(["missing-follow-up-id"])
    await confirm_follow_up_delivery(delivered=False)


@pytest.mark.asyncio
async def test_confirm_delivery_handles_store_exception() -> None:
    from unittest.mock import AsyncMock, patch

    from app.core.memory.proactive.delivery_tracker import (
        confirm_follow_up_delivery,
        register_follow_up_attempts,
        reset_follow_up_delivery,
    )

    reset_follow_up_delivery()
    register_follow_up_attempts(["cm_exc"])
    mock_store = AsyncMock()
    mock_store.mark_status = AsyncMock(side_effect=RuntimeError("db down"))

    with patch(
        "app.core.memory.proactive.sqlite_store.SqlAlchemyCommitmentStore",
        return_value=mock_store,
    ):
        await confirm_follow_up_delivery(delivered=True)
