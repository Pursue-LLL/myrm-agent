"""Memory events in a session trace carry real epoch times, whatever zone the server's clock is set to."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.statistics.session_trace_enrichment import _build_session_memory_events
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService


@pytest.fixture
def server_clock_at_utc_plus_8(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Put the process clock at UTC+8, so reading a UTC wall time as local time is off by eight hours."""
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _event(occurred_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id="evt-1",
        kind="write",
        status="applied",
        occurred_at=occurred_at,
        memory_type="fact",
        summary="remembered a preference",
        target_kind="memory",
        target_id="mem-1",
        influence_refs_json=None,
        metadata_json=None,
    )


async def _timestamps(occurred_at: datetime) -> list[object]:
    ledger_rows = AsyncMock(return_value=[_event(occurred_at)])
    with patch.object(MemoryOperationLedgerService, "list_events_for_session", new=ledger_rows):
        events = await _build_session_memory_events(MagicMock(), "chat-1")
    return [event["timestamp"] for event in events]


async def test_a_stored_utc_wall_time_is_read_as_utc(server_clock_at_utc_plus_8: None) -> None:
    # SQLite hands the stored UTC wall time back without a zone.
    stored = datetime(2026, 11, 11, 12, 0)

    assert await _timestamps(stored) == [datetime(2026, 11, 11, 12, 0, tzinfo=UTC).timestamp()]


async def test_a_zoned_time_keeps_its_instant(server_clock_at_utc_plus_8: None) -> None:
    zoned = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)

    assert await _timestamps(zoned) == [zoned.timestamp()]
