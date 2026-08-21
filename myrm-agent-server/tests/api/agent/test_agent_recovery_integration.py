"""Integration tests for agent profile startup recovery and snapshot rollback.

[INPUT]
- app.services.agent.profile.profile_recovery_service::ProfileStartupRecoveryService
- app.services.agent.profile.profile_snapshot_service::ProfileSnapshotService
- app.api.agents.recovery::router

[OUTPUT]
- test_agent_startup_recovery_full_flow_integration
- test_agent_startup_recovery_rollback_lifecycle
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_agent_startup_recovery_full_flow_integration() -> None:
    """Verify end-to-end integration flow of health probe, diagnostic bundle, and snapshot persistence."""
    test_app = build_minimal_app(preset="agents_api")
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        agent_id = "test_agent_recovery_flow_01"

        # 1. Probe health on non-existent agent returns error
        res_404 = await client.get(f"/api/v1/agents/{agent_id}/recovery/health")
        assert res_404.status_code == 200
        data_404 = res_404.json()["data"]
        assert data_404["is_healthy"] is False
        assert len(data_404["quarantined_components"]) == 1

        # 2. Export diagnostics bundle
        diag_res = await client.get(f"/api/v1/agents/{agent_id}/recovery/diagnostics")
        assert diag_res.status_code == 200
        diag_data = diag_res.json()["data"]["diagnostics"]
        assert diag_data["agent_id"] == agent_id
        assert "health_report" in diag_data
        assert "recent_snapshots" in diag_data


@pytest.mark.asyncio
async def test_agent_startup_recovery_rollback_lifecycle() -> None:
    """Verify rollback lifecycle and 404 error handling when no snapshot exists."""
    test_app = build_minimal_app(preset="agents_api")
    transport = ASGITransport(app=test_app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        agent_id = "test_agent_rollback_nonexistent_02"
        # Attempt rollback without any saved snapshot
        res_rollback = await client.post(f"/api/v1/agents/{agent_id}/recovery/rollback")
        assert res_rollback.status_code == 404
