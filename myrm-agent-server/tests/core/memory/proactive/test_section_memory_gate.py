"""Tests for proactive follow-up heartbeat section."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.cron.situation import SituationContext


@pytest.mark.asyncio
async def test_pending_section_skips_when_memory_disabled() -> None:
    from app.core.memory.proactive.section import PendingCommitmentsSection

    section = PendingCommitmentsSection()
    ctx = SituationContext(
        last_tick_at=datetime.now(UTC),
        agent_id="agent-1",
        user_id="default",
        memory_enabled=False,
    )
    result = await section.build(ctx)
    assert result is None


@pytest.mark.asyncio
async def test_pending_section_skips_when_daily_cap_reached() -> None:
    from app.core.memory.proactive.section import PendingCommitmentsSection

    section = PendingCommitmentsSection()
    ctx = SituationContext(
        last_tick_at=datetime.now(UTC),
        agent_id="agent-1",
        user_id="default",
        memory_enabled=True,
    )
    mock_store = MagicMock()
    mock_store.expire_stale = AsyncMock(return_value=0)
    mock_store.count_sent_rolling = AsyncMock(return_value=3)
    mock_store.list_due = AsyncMock()

    with patch(
        "app.core.memory.proactive.sqlite_store.SqlAlchemyCommitmentStore",
        return_value=mock_store,
    ):
        result = await section.build(ctx)

    assert result is None
    mock_store.list_due.assert_not_called()


@pytest.mark.asyncio
async def test_pending_section_expires_and_respects_remaining_daily_quota() -> None:
    from myrm_agent_harness.toolkits.memory.proactive.types import (
        CommitmentDueWindow,
        CommitmentKind,
        CommitmentRecord,
        CommitmentSensitivity,
        CommitmentStatus,
    )

    from app.core.memory.proactive.section import PendingCommitmentsSection

    record = CommitmentRecord(
        id="c1",
        agent_id="agent-1",
        user_id="default",
        channel="web",
        kind=CommitmentKind.EVENT_CHECK_IN,
        sensitivity=CommitmentSensitivity.ROUTINE,
        status=CommitmentStatus.PENDING,
        reason="interview",
        suggested_text="Check in on interview",
        dedupe_key="k1",
        confidence=0.9,
        due_window=CommitmentDueWindow(earliest_ms=0, latest_ms=999_999_999_999, timezone="UTC"),
    )

    section = PendingCommitmentsSection()
    ctx = SituationContext(
        last_tick_at=datetime.now(UTC),
        agent_id="agent-1",
        user_id="default",
        memory_enabled=True,
    )
    mock_store = MagicMock()
    mock_store.expire_stale = AsyncMock(return_value=1)
    mock_store.count_sent_rolling = AsyncMock(return_value=1)
    mock_store.list_due = AsyncMock(return_value=[record])
    mock_store.mark_attempted = AsyncMock(return_value=1)

    with patch(
        "app.core.memory.proactive.sqlite_store.SqlAlchemyCommitmentStore",
        return_value=mock_store,
    ):
        with patch(
            "app.core.memory.proactive.delivery_tracker.register_follow_up_attempts",
        ) as register_mock:
            result = await section.build(ctx)

    assert result is not None
    assert "Check in on interview" in result
    mock_store.expire_stale.assert_awaited_once()
    mock_store.list_due.assert_awaited_once()
    call_kwargs = mock_store.list_due.await_args.kwargs
    assert call_kwargs["limit"] == 2
    register_mock.assert_called_once_with(["c1"])


@pytest.mark.asyncio
async def test_pending_section_returns_none_when_no_due_items() -> None:
    from app.core.memory.proactive.section import PendingCommitmentsSection

    section = PendingCommitmentsSection()
    ctx = SituationContext(
        last_tick_at=datetime.now(UTC),
        agent_id="agent-empty-due",
        user_id="default",
        memory_enabled=True,
    )
    mock_store = MagicMock()
    mock_store.expire_stale = AsyncMock(return_value=0)
    mock_store.count_sent_rolling = AsyncMock(return_value=0)
    mock_store.list_due = AsyncMock(return_value=[])

    with patch(
        "app.core.memory.proactive.sqlite_store.SqlAlchemyCommitmentStore",
        return_value=mock_store,
    ):
        result = await section.build(ctx)

    assert result is None


@pytest.mark.asyncio
async def test_pending_section_tolerates_mark_attempted_failure() -> None:
    from myrm_agent_harness.toolkits.memory.proactive.types import (
        CommitmentDueWindow,
        CommitmentKind,
        CommitmentRecord,
        CommitmentSensitivity,
        CommitmentStatus,
    )

    from app.core.memory.proactive.section import PendingCommitmentsSection

    record = CommitmentRecord(
        id="c_fail",
        agent_id="agent-mark-fail",
        user_id="default",
        channel="web",
        kind=CommitmentKind.OPEN_LOOP,
        sensitivity=CommitmentSensitivity.ROUTINE,
        status=CommitmentStatus.PENDING,
        reason="test",
        suggested_text="ping",
        dedupe_key="k_fail",
        confidence=0.8,
        due_window=CommitmentDueWindow(earliest_ms=0, latest_ms=999_999_999_999, timezone="UTC"),
    )

    section = PendingCommitmentsSection()
    ctx = SituationContext(
        last_tick_at=datetime.now(UTC),
        agent_id="agent-mark-fail",
        user_id="default",
        memory_enabled=True,
    )
    mock_store = MagicMock()
    mock_store.expire_stale = AsyncMock(return_value=0)
    mock_store.count_sent_rolling = AsyncMock(return_value=0)
    mock_store.list_due = AsyncMock(return_value=[record])
    mock_store.mark_attempted = AsyncMock(side_effect=RuntimeError("db"))

    with patch(
        "app.core.memory.proactive.sqlite_store.SqlAlchemyCommitmentStore",
        return_value=mock_store,
    ):
        with patch("app.core.memory.proactive.delivery_tracker.register_follow_up_attempts"):
            result = await section.build(ctx)

    assert result is not None
    assert "ping" in result
