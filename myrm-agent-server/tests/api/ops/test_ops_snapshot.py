"""Tests for Ops Aggregated Snapshot API and Service.

[INPUT]
- app.schemas.ops::OpsAggregatedSnapshot
- app.services.ops.snapshot_service::OpsAggregatedSnapshotService
- app.api.ops.router::router

[OUTPUT]
- Unit and integration tests for GET /api/v1/ops/snapshot
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.schemas.ops import OpsAggregatedSnapshot
from app.services.ops.snapshot_service import OpsAggregatedSnapshotService
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")


@pytest.mark.asyncio
async def test_ops_aggregated_snapshot_service_collects_successfully() -> None:
    """Verify that OpsAggregatedSnapshotService produces a fully populated DTO."""
    snapshot = await OpsAggregatedSnapshotService.collect_snapshot(include_doctor=False)

    assert isinstance(snapshot, OpsAggregatedSnapshot)
    assert snapshot.system.app_name is not None
    assert snapshot.system.os is not None
    assert snapshot.system.uptime_seconds >= 0.0

    assert snapshot.liveness.state in ("idle", "busy", "degraded", "draining")
    assert snapshot.liveness.max_concurrent > 0

    assert snapshot.resources.memory_level is not None
    assert snapshot.resources.idle_reclaim_timeout_seconds >= 0.0

    assert isinstance(snapshot.channels.total_channels, int)
    assert isinstance(snapshot.channels.channels, dict)

    assert snapshot.governance.cron_failures_24h >= 0
    assert snapshot.governance.pending_approvals >= 0

    assert snapshot.usage_radar.total_calls >= 0
    assert snapshot.usage_radar.total_tokens >= 0
    assert snapshot.usage_radar.total_usd >= 0.0

    assert snapshot.memory.health_status in (
        "healthy",
        "degraded",
        "critical",
        "unknown",
    )
    assert snapshot.doctor_summary is None


@pytest.mark.asyncio
async def test_ops_aggregated_snapshot_with_doctor_summary() -> None:
    """Verify snapshot collection when include_doctor is enabled."""
    snapshot = await OpsAggregatedSnapshotService.collect_snapshot(include_doctor=True)

    assert isinstance(snapshot, OpsAggregatedSnapshot)
    assert snapshot.doctor_summary is not None
    assert snapshot.doctor_summary.status in ("pass", "warn", "fail")
    assert snapshot.doctor_summary.harness_total >= 0
    assert snapshot.doctor_summary.server_total >= 0


@pytest.mark.asyncio
async def test_get_ops_snapshot_api_endpoint() -> None:
    """Verify GET /api/v1/ops/snapshot endpoint returns 200 with schema matching."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/ops/snapshot?include_doctor=false")
        assert response.status_code == 200

        data = response.json()
        assert "system" in data
        assert "liveness" in data
        assert "resources" in data
        assert "channels" in data
        assert "governance" in data
        assert "usage_radar" in data
        assert "memory" in data
        assert data.get("doctor_summary") is None

        # Verify parsed schema validation
        parsed = OpsAggregatedSnapshot.model_validate(data)
        assert parsed.system.app_name is not None
        assert parsed.liveness.state in ("idle", "busy", "degraded", "draining")


@pytest.mark.asyncio
async def test_collect_memory_info_counts_error_ledger_rows() -> None:
    """Memory ops block must query server ledger with ERROR status (not harness FAILED)."""
    scalar_calls = 0

    class _FakeSession:
        async def scalar(self, _stmt: object) -> int:
            nonlocal scalar_calls
            scalar_calls += 1
            if scalar_calls == 1:
                return 12
            if scalar_calls == 2:
                return 3
            return 2

    @asynccontextmanager
    async def _fake_get_session():
        yield _FakeSession()

    with patch(
        "app.services.ops.snapshot_service.get_session",
        _fake_get_session,
    ):
        info = await OpsAggregatedSnapshotService._collect_memory_info()

    assert info.event_count == 12
    assert info.failed_event_count == 3
    assert info.queue_backlog == 2
    assert info.health_status == "degraded"
    assert scalar_calls == 3


@pytest.mark.asyncio
async def test_collect_memory_info_probe_failure_is_critical() -> None:
    @asynccontextmanager
    async def _broken_get_session():
        raise RuntimeError("db unavailable")
        yield  # pragma: no cover

    with patch(
        "app.services.ops.snapshot_service.get_session",
        _broken_get_session,
    ):
        info = await OpsAggregatedSnapshotService._collect_memory_info()

    assert info.health_status == "critical"
    assert info.event_count == 0


@pytest.mark.asyncio
async def test_ops_snapshot_subtask_isolation_and_fallback() -> None:
    """Verify that when a subtask raises an unexpected error, the snapshot falls back gracefully."""
    from unittest.mock import patch

    with patch.object(
        OpsAggregatedSnapshotService,
        "_collect_governance_info",
        side_effect=RuntimeError("Simulated governance DB crash"),
    ):
        snapshot = await OpsAggregatedSnapshotService.collect_snapshot(include_doctor=False)
        assert isinstance(snapshot, OpsAggregatedSnapshot)
        assert snapshot.governance.cron_failures_24h == 0
        assert snapshot.governance.pending_approvals == 0
        assert snapshot.system.app_name is not None
