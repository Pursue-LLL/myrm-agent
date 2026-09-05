"""Unit tests for TraceExportSecurityDiagnostic and local-only trace gate."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.infra.health.server_diagnostics import (
    ServerDiagnosticsManager,
    TraceExportSecurityDiagnostic,
)


@pytest.mark.asyncio
async def test_trace_security_diagnostic_local_trace_only_pass() -> None:
    diagnostic = TraceExportSecurityDiagnostic()
    with (
        patch.dict("os.environ", {"MYRM_LOCAL_TRACE_ONLY": "1", "OTEL_EXPORTER_OTLP_ENDPOINT": ""}),
    ):
        report = await diagnostic.check_health()
        assert report.status == "pass"
        assert report.code == "OK_LOCAL_TRACE_ONLY_ENFORCED"
        assert report.component_name == "TraceExportSecurity"


@pytest.mark.asyncio
async def test_trace_security_diagnostic_local_mode_with_remote_endpoint_warns() -> None:
    diagnostic = TraceExportSecurityDiagnostic()
    with (
        patch.dict(
            "os.environ",
            {
                "MYRM_LOCAL_TRACE_ONLY": "true",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "https://remote-collector.corp:4317",
            },
        ),
    ):
        report = await diagnostic.check_health()
        assert report.status == "warn"
        assert report.code == "WARN_REMOTE_TRACE_IN_LOCAL_MODE"
        assert "blocked" in report.message


@pytest.mark.asyncio
async def test_trace_security_diagnostic_normal_mode_with_otlp_active() -> None:
    diagnostic = TraceExportSecurityDiagnostic()
    with (
        patch.dict(
            "os.environ",
            {
                "MYRM_LOCAL_TRACE_ONLY": "0",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            },
        ),
    ):
        report = await diagnostic.check_health()
        assert report.status == "pass"
        assert report.code == "OK_OTLP_EXPORT_ACTIVE"


@pytest.mark.asyncio
async def test_trace_security_diagnostic_normal_mode_noop() -> None:
    diagnostic = TraceExportSecurityDiagnostic()
    with (
        patch.dict("os.environ", {"MYRM_LOCAL_TRACE_ONLY": "0", "OTEL_EXPORTER_OTLP_ENDPOINT": ""}),
    ):
        report = await diagnostic.check_health()
        assert report.status == "pass"
        assert report.code == "OK_LOCAL_NOOP_ACTIVE"


@pytest.mark.asyncio
async def test_server_diagnostics_manager_includes_trace_security() -> None:
    manager = ServerDiagnosticsManager()
    probe_names = [p.__class__.__name__ for p in manager._probes]
    assert "TraceExportSecurityDiagnostic" in probe_names

    reports = await manager.run_all()
    component_names = [r.component_name for r in reports]
    assert "TraceExportSecurity" in component_names


def test_assert_local_trace_only_blocks_remote() -> None:
    from myrm_agent_harness.infra.tracing import (
        assert_local_trace_only,
        is_local_trace_only,
    )

    with patch.dict("os.environ", {"MYRM_LOCAL_TRACE_ONLY": "1"}):
        assert is_local_trace_only() is True
        # localhost permitted
        assert_local_trace_only("http://localhost:4317")
        assert_local_trace_only("http://127.0.0.1:4318")

        # remote endpoint raises PermissionError
        with pytest.raises(PermissionError) as exc_info:
            assert_local_trace_only("https://otlp.datadoghq.com")
        assert "Remote trace export" in str(exc_info.value)
