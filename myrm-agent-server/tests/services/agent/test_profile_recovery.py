"""Unit and integration tests for ProfileStartupRecoveryService and endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.agent.profile.profile_recovery_service import (
    ProfileStartupRecoveryService,
)
from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_probe_profile_health_not_found():
    report = await ProfileStartupRecoveryService.probe_profile_health("non_existent_agent_999")
    assert report.is_healthy is False
    assert len(report.quarantined_components) == 1
    assert report.quarantined_components[0].status == "error"


@pytest.mark.asyncio
async def test_export_diagnostics():
    diagnostics = await ProfileStartupRecoveryService.export_diagnostics("non_existent_agent_999")
    assert "agent_id" in diagnostics
    assert "health_report" in diagnostics
    assert "recent_snapshots" in diagnostics


@pytest.mark.asyncio
async def test_recovery_api_endpoints():
    test_app = build_minimal_app(preset="agents_api")
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test health probe
        res = await client.get("/api/v1/agents/test_agent_123/recovery/health")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "is_healthy" in data
        assert "healthy_components" in data

        # Test diagnostics
        diag_res = await client.get("/api/v1/agents/test_agent_123/recovery/diagnostics")
        assert diag_res.status_code == 200
        assert "diagnostics" in diag_res.json()["data"]
