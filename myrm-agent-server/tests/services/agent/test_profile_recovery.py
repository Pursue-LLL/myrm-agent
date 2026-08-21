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
async def test_probe_single_model():
    # Empty or None model inherits default
    res_default = await ProfileStartupRecoveryService._probe_single_model(None)
    assert res_default.status == "healthy"
    assert res_default.component_id == "default_inherited"

    # Valid model ID
    res_valid = await ProfileStartupRecoveryService._probe_single_model("claude-3-7-sonnet")
    assert res_valid.status == "healthy"
    assert res_valid.component_id == "claude-3-7-sonnet"

    # Invalid model ID with newline injection
    res_invalid = await ProfileStartupRecoveryService._probe_single_model("invalid\nmodel")
    assert res_invalid.status == "quarantined"


@pytest.mark.asyncio
async def test_probe_single_builtin_tool():
    # Valid baseline tool
    res_valid = await ProfileStartupRecoveryService._probe_single_builtin_tool("file_ops")
    assert res_valid.status == "healthy"
    assert res_valid.component_type == "builtin_tool"

    # Valid togglable tool
    res_search = await ProfileStartupRecoveryService._probe_single_builtin_tool("web_search")
    assert res_search.status == "healthy"

    # Empty tool
    res_empty = await ProfileStartupRecoveryService._probe_single_builtin_tool("")
    assert res_empty.status == "quarantined"

    # Unknown tool
    res_unknown = await ProfileStartupRecoveryService._probe_single_builtin_tool("non_existent_tool_xyz")
    assert res_unknown.status == "quarantined"


@pytest.mark.asyncio
async def test_probe_single_mcp():
    # Empty mcp
    res_empty = await ProfileStartupRecoveryService._probe_single_mcp("")
    assert res_empty.status == "quarantined"

    # Command exists in PATH
    res_sh = await ProfileStartupRecoveryService._probe_single_mcp("sh -c echo")
    assert res_sh.status == "healthy"

    # Non-existent executable
    res_unknown = await ProfileStartupRecoveryService._probe_single_mcp("non_existent_command_xyz_12345")
    assert res_unknown.status == "quarantined"


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
