"""Tests for System Telemetry Posture API endpoint.

[INPUT]
- app.api.system.router::router
- httpx::ASGITransport, AsyncClient

[OUTPUT]
- test_telemetry_posture_endpoint_returns_valid_shape

[POS]
Server integration tests for SRE OpenTelemetry diagnostic posture.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_telemetry_posture_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://apm.internal:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer%20test123")

    app = build_minimal_app("system")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/system/telemetry-posture")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["protocol"] == "http/protobuf"
        assert data["headers_configured"] is True
        assert data["three_tier_semantics"] is True
        assert data["prompt_cache_metering"] is True
        assert data["endpoint"] == "http://apm.internal:4318"
        assert "exporter_type" in data
        assert "degraded_reason" in data


@pytest.mark.asyncio
async def test_telemetry_posture_endpoint_degraded_state(monkeypatch) -> None:
    """Test API correctly surfaces degraded_console status when OTLP exporter fails."""
    from unittest.mock import patch

    with patch(
        "myrm_agent_harness.infra.tracing.get_telemetry_posture",
        return_value={
            "status": "degraded_console",
            "initialized": True,
            "has_sdk": True,
            "endpoint": "http://broken.internal:4318",
            "protocol": "http/protobuf",
            "headers_configured": False,
            "local_trace_only": False,
            "exporter_type": "console",
            "degraded_reason": "OTLP export fallback to console: connection refused",
            "three_tier_semantics": True,
            "prompt_cache_metering": True,
        },
    ):
        app = build_minimal_app("system")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/system/telemetry-posture")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded_console"
            assert data["exporter_type"] == "console"
            assert "fallback to console" in data["degraded_reason"]


@pytest.mark.asyncio
async def test_telemetry_posture_real_harness_integration() -> None:
    """Test full integration chain from real FastAPI router to real harness get_telemetry_posture (No Mock)."""
    app = build_minimal_app("system")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/system/telemetry-posture")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("active", "console", "noop", "missing_sdk", "local_only", "degraded_console")
        assert "initialized" in data
        assert "has_sdk" in data
        assert "protocol" in data
        assert "three_tier_semantics" in data
        assert data["three_tier_semantics"] is True
        assert data["prompt_cache_metering"] is True
        assert "git_branch" in data
        assert "git_commit" in data


