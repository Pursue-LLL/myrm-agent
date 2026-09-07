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
