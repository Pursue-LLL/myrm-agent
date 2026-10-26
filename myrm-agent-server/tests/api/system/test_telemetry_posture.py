"""Tests for the System Telemetry Posture API endpoint.

[INPUT]
- app.api.system.router::router
- httpx::ASGITransport, AsyncClient

[OUTPUT]
- Tests that the endpoint serves the harness's measured posture unchanged and never an asserted one.

[POS]
Server integration tests for SRE OpenTelemetry diagnostic posture.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

_REMOVED_ASSERTED_FLAGS = ("three_tier_semantics", "prompt_cache_metering")
_MEASURED_FIELDS = (
    "sampler",
    "content_capture",
    "metrics_exporting",
    "exported_spans",
    "failed_batches",
    "withheld_spans",
    "last_success_at",
    "last_failure_at",
)


@pytest.fixture(autouse=True)
def _standard_otlp_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_TRACES_EXPORTER",
        "OTEL_SDK_DISABLED",
        "MYRM_LOCAL_TRACE_ONLY",
    ):
        monkeypatch.delenv(name, raising=False)


async def _get_posture() -> dict[str, object]:
    app = build_minimal_app("system")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/system/telemetry-posture")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_posture_shows_the_configured_target_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:s3cret@apm.internal:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer%20test123")

    data = await _get_posture()

    assert data["protocol"] == "http/protobuf"
    assert data["headers_configured"] is True
    assert str(data["endpoint"]).endswith("apm.internal:4318/v1/traces")
    assert "s3cret" not in json.dumps(data)
    assert "test123" not in json.dumps(data)


@pytest.mark.asyncio
async def test_posture_carries_measured_fields_and_none_of_the_removed_asserted_flags() -> None:
    data = await _get_posture()

    for name in _MEASURED_FIELDS:
        assert name in data
    for name in _REMOVED_ASSERTED_FLAGS:
        assert name not in data
    assert data["status"] in {"noop", "missing_sdk", "disabled", "local_only"}
    assert data["exported_spans"] == 0
    assert data["metrics_exporting"] is False
    assert data["content_capture"] is False


@pytest.mark.asyncio
async def test_posture_with_the_kill_switch_reports_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://apm.internal:4318")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    data = await _get_posture()

    assert data["status"] == "disabled"


@pytest.mark.asyncio
async def test_posture_surfaces_a_failing_pipeline_with_its_counters() -> None:
    failing = {
        "status": "failing",
        "initialized": True,
        "has_sdk": True,
        "endpoint": "http://broken.internal:4318/v1/traces",
        "protocol": "http/protobuf",
        "headers_configured": False,
        "local_trace_only": False,
        "exporter_type": "otlp_http",
        "degraded_reason": None,
        "sampler": "ParentBased(root=TraceIdRatioBased(0.1))",
        "content_capture": False,
        "metrics_exporting": True,
        "exported_spans": 12,
        "failed_batches": 3,
        "withheld_spans": 5,
        "last_success_at": 1_700_000_000.0,
        "last_failure_at": 1_700_000_060.0,
        "git_branch": None,
        "git_commit": None,
    }
    with patch("myrm_agent_harness.infra.tracing.get_telemetry_posture", return_value=failing):
        data = await _get_posture()

    assert data["status"] == "failing"
    assert data["failed_batches"] == 3
    assert data["withheld_spans"] == 5
    assert data["last_failure_at"] == 1_700_000_060.0
    assert data["sampler"] == "ParentBased(root=TraceIdRatioBased(0.1))"


@pytest.mark.asyncio
async def test_posture_reports_an_error_status_when_the_harness_probe_raises() -> None:
    with patch("myrm_agent_harness.infra.tracing.get_telemetry_posture", side_effect=RuntimeError("probe broke")):
        data = await _get_posture()

    assert data["status"] == "error"
    assert data["error"] == "probe broke"
    assert data["initialized"] is False
    for name in _REMOVED_ASSERTED_FLAGS:
        assert name not in data
