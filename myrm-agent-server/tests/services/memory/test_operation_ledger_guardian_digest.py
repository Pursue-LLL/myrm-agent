"""Tests for guardian morning digest aggregation semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.database.models.memory import MemoryHealthSnapshotModel, MemoryOperationEventModel
from app.services.memory.guardian_policy import MemoryGuardianPolicy
from app.services.memory.operation_ledger import (
    MemoryOperationLedgerService,
    _resolve_guardian_digest_window,
    guardian_guard_alert_thresholds,
)


class _FakeExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_FakeExecuteResult":
        return self

    def all(self) -> list[object]:
        return self._rows


@pytest.mark.asyncio
async def test_latest_guardian_morning_digest_aggregates_window_events(monkeypatch: pytest.MonkeyPatch) -> None:
    window_start = datetime(2026, 1, 2, 22, 0, tzinfo=UTC)
    window_end = datetime(2026, 1, 3, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "app.services.memory.operation_ledger._resolve_guardian_digest_window",
        lambda *, policy: (window_start, window_end, "quiet_window"),
    )

    event_new = MemoryOperationEventModel(
        id="evt-new",
        kind="maintenance",
        status="success",
        occurred_at=datetime(2026, 1, 3, 5, 30, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian maintenance: merged 1",
        metadata_json={
            "forgotten_count": 2,
            "archived_count": 1,
            "merged_count": 3,
            "corrected_count": 1,
            "staleness_removed": 0,
            "staleness_extended": 2,
            "duration_ms": 1200,
            "forced": True,
        },
    )
    event_old = MemoryOperationEventModel(
        id="evt-old",
        kind="maintenance",
        status="success",
        occurred_at=datetime(2026, 1, 3, 1, 20, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian maintenance: merged 2",
        metadata_json={
            "forgotten_count": 1,
            "archived_count": 0,
            "merged_count": 2,
            "corrected_count": 2,
            "staleness_removed": 1,
            "staleness_extended": 0,
            "duration_ms": 800,
            "forced": False,
        },
    )
    snapshot_a = MemoryHealthSnapshotModel(
        id="snap-a",
        status="unhealthy",
        total=64,
        dimensions_json={},
        suggestions_json=[],
        has_graph=False,
        sample_size=0,
        guardian_running=True,
        seconds_until_next=3600,
        checked_at=datetime(2026, 1, 3, 1, 30, tzinfo=UTC),
        ttl_seconds=3600,
    )
    snapshot_b = MemoryHealthSnapshotModel(
        id="snap-b",
        status="healthy",
        total=78,
        dimensions_json={},
        suggestions_json=[],
        has_graph=False,
        sample_size=0,
        guardian_running=True,
        seconds_until_next=7200,
        checked_at=datetime(2026, 1, 3, 5, 40, tzinfo=UTC),
        ttl_seconds=3600,
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _FakeExecuteResult([event_new, event_old]),
            _FakeExecuteResult([snapshot_a, snapshot_b]),
        ]
    )
    service = MemoryOperationLedgerService(db)

    digest = await service.latest_guardian_morning_digest(
        policy=MemoryGuardianPolicy(quiet_window_enabled=True, quiet_window_start_hour=22, quiet_window_end_hour=6)
    )

    assert digest["available"] is True
    assert digest["event_count"] == 2
    assert digest["forced_runs"] == 1
    assert digest["scheduled_runs"] == 1
    assert digest["counts"] == {
        "forgotten": 3,
        "archived": 1,
        "merged": 5,
        "corrected": 3,
        "stale_removed": 1,
        "stale_extended": 2,
    }
    assert digest["duration_ms"] == 2000
    assert digest["health_total"] == 78
    assert digest["health_delta"] == 14
    assert digest["health_status"] == "healthy"
    assert digest["window_mode"] == "quiet_window"
    assert digest["window_started_at"] == window_start.isoformat()
    assert digest["window_ended_at"] == window_end.isoformat()


@pytest.mark.asyncio
async def test_latest_guardian_morning_digest_returns_unavailable_when_no_window_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window_start = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
    window_end = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "app.services.memory.operation_ledger._resolve_guardian_digest_window",
        lambda *, policy: (window_start, window_end, "rolling_24h"),
    )

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_FakeExecuteResult([])])
    service = MemoryOperationLedgerService(db)

    digest = await service.latest_guardian_morning_digest(policy=MemoryGuardianPolicy())

    assert digest == {
        "available": False,
        "window_started_at": window_start.isoformat(),
        "window_ended_at": window_end.isoformat(),
        "window_mode": "rolling_24h",
    }


def test_resolve_guardian_digest_window_for_overnight_quiet_window() -> None:
    policy = MemoryGuardianPolicy(
        quiet_window_enabled=True,
        quiet_window_start_hour=22,
        quiet_window_end_hour=6,
        timezone_offset_minutes=0,
    )
    start, end, mode = _resolve_guardian_digest_window(
        policy=policy,
        now_utc=datetime(2026, 1, 3, 3, 0, tzinfo=UTC),
    )

    assert mode == "quiet_window"
    assert start == datetime(2026, 1, 1, 22, 0, tzinfo=UTC)
    assert end == datetime(2026, 1, 2, 6, 0, tzinfo=UTC)


def test_resolve_guardian_digest_window_for_regular_quiet_window() -> None:
    policy = MemoryGuardianPolicy(
        quiet_window_enabled=True,
        quiet_window_start_hour=1,
        quiet_window_end_hour=5,
        timezone_offset_minutes=0,
    )
    start, end, mode = _resolve_guardian_digest_window(
        policy=policy,
        now_utc=datetime(2026, 1, 3, 8, 0, tzinfo=UTC),
    )

    assert mode == "quiet_window"
    assert start == datetime(2026, 1, 3, 1, 0, tzinfo=UTC)
    assert end == datetime(2026, 1, 3, 5, 0, tzinfo=UTC)


def test_resolve_guardian_digest_window_falls_back_to_rolling_24h() -> None:
    policy = MemoryGuardianPolicy(quiet_window_enabled=False, timezone_offset_minutes=0)
    now_utc = datetime(2026, 1, 3, 10, 0, tzinfo=UTC)

    start, end, mode = _resolve_guardian_digest_window(policy=policy, now_utc=now_utc)

    assert mode == "rolling_24h"
    assert start == datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    assert end == now_utc


@pytest.mark.asyncio
async def test_guardian_guard_alert_snapshot_aggregates_warning_reasons() -> None:
    warning_new = MemoryOperationEventModel(
        id="warn-1",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "budget_guard_unavailable",
        },
    )
    warning_old = MemoryOperationEventModel(
        id="warn-2",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 8, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "capacity_guard_unavailable",
        },
    )
    unrelated_warning = MemoryOperationEventModel(
        id="warn-3",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 7, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Unrelated warning event.",
        metadata_json={"operation": "other_warning"},
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_FakeExecuteResult([warning_new, warning_old, unrelated_warning])])
    service = MemoryOperationLedgerService(db)

    snapshot = await service.guardian_guard_alert_snapshot(lookback_hours=24)

    assert snapshot["active"] is True
    assert snapshot["escalated"] is False
    assert snapshot["window_hours"] == 24
    assert snapshot["total"] == 2
    assert snapshot["reasons"] == {
        "budget_guard_unavailable": 1,
        "capacity_guard_unavailable": 1,
    }
    assert snapshot["dominant_reason"] == "budget_guard_unavailable"
    assert snapshot["dominant_reason_count"] == 1
    assert snapshot["dominant_reason_ratio"] == 0.5
    assert snapshot["thresholds"] == guardian_guard_alert_thresholds()
    assert snapshot["last_occurred_at"] == datetime(2026, 1, 3, 10, 0, tzinfo=UTC).isoformat()


@pytest.mark.asyncio
async def test_guardian_guard_alert_snapshot_returns_inactive_when_no_guard_warning() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_FakeExecuteResult([])])
    service = MemoryOperationLedgerService(db)

    snapshot = await service.guardian_guard_alert_snapshot(lookback_hours=24)

    assert snapshot == {
        "active": False,
        "escalated": False,
        "window_hours": 24,
        "total": 0,
        "reasons": {},
        "dominant_reason": None,
        "dominant_reason_count": 0,
        "dominant_reason_ratio": 0.0,
        "thresholds": guardian_guard_alert_thresholds(),
        "last_occurred_at": None,
    }


@pytest.mark.asyncio
async def test_guardian_guard_alert_snapshot_requires_min_total_events() -> None:
    warning_one = MemoryOperationEventModel(
        id="warn-one",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "budget_guard_unavailable",
        },
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_FakeExecuteResult([warning_one])])
    service = MemoryOperationLedgerService(db)

    snapshot = await service.guardian_guard_alert_snapshot(lookback_hours=24)

    assert snapshot["active"] is False
    assert snapshot["total"] == 1
    assert snapshot["reasons"] == {"budget_guard_unavailable": 1}


@pytest.mark.asyncio
async def test_guardian_guard_alert_snapshot_escalates_when_one_reason_dominates() -> None:
    warning_one = MemoryOperationEventModel(
        id="warn-one",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "budget_guard_unavailable",
        },
    )
    warning_two = MemoryOperationEventModel(
        id="warn-two",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "budget_guard_unavailable",
        },
    )
    warning_three = MemoryOperationEventModel(
        id="warn-three",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 8, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "capacity_guard_unavailable",
        },
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_FakeExecuteResult([warning_one, warning_two, warning_three])])
    service = MemoryOperationLedgerService(db)

    snapshot = await service.guardian_guard_alert_snapshot(lookback_hours=24)

    assert snapshot["active"] is True
    assert snapshot["escalated"] is True
    assert snapshot["dominant_reason"] == "budget_guard_unavailable"
    assert snapshot["dominant_reason_count"] == 2
    assert snapshot["dominant_reason_ratio"] == pytest.approx(2 / 3, rel=1e-6)
    assert snapshot["thresholds"] == guardian_guard_alert_thresholds()


@pytest.mark.asyncio
async def test_guardian_guard_alert_snapshot_uses_aggressive_threshold_profile() -> None:
    warning_one = MemoryOperationEventModel(
        id="warn-a1",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "budget_guard_unavailable",
        },
    )
    warning_two = MemoryOperationEventModel(
        id="warn-a2",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "budget_guard_unavailable",
        },
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_FakeExecuteResult([warning_one, warning_two])])
    service = MemoryOperationLedgerService(db)

    snapshot = await service.guardian_guard_alert_snapshot(
        lookback_hours=24,
        frequency_tier="aggressive",
    )

    assert snapshot["active"] is False
    assert snapshot["escalated"] is False
    assert snapshot["thresholds"] == guardian_guard_alert_thresholds(frequency_tier="aggressive")


@pytest.mark.asyncio
async def test_guardian_guard_alert_snapshot_uses_conservative_threshold_profile() -> None:
    warning_one = MemoryOperationEventModel(
        id="warn-c1",
        kind="maintenance",
        status="warning",
        occurred_at=datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
        source="memory_guardian",
        summary="Guardian paused for safety due to temporary dependency status.",
        metadata_json={
            "operation": "guard_unavailable_skip",
            "reason": "capacity_guard_unavailable",
        },
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_FakeExecuteResult([warning_one])])
    service = MemoryOperationLedgerService(db)

    snapshot = await service.guardian_guard_alert_snapshot(
        lookback_hours=24,
        frequency_tier="conservative",
    )

    assert snapshot["active"] is True
    assert snapshot["escalated"] is False
    assert snapshot["thresholds"] == guardian_guard_alert_thresholds(frequency_tier="conservative")
