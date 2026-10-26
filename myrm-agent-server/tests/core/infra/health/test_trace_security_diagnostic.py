"""Unit tests for TraceExportSecurityDiagnostic and local-only trace gate."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.infra.health.server_diagnostics import (
    ServerDiagnosticsManager,
    TraceExportSecurityDiagnostic,
)


@pytest.fixture(autouse=True)
def _clean_otlp_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_SDK_DISABLED",
        "MYRM_LOCAL_TRACE_ONLY",
    ):
        monkeypatch.delenv(name, raising=False)


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
async def test_local_only_judges_the_parsed_host_and_never_prints_credentials() -> None:
    env = {"MYRM_LOCAL_TRACE_ONLY": "1", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:hunter2@attacker.example:4318"}
    with patch.dict("os.environ", env):
        report = await TraceExportSecurityDiagnostic().check_health()
    assert report.code == "WARN_REMOTE_TRACE_IN_LOCAL_MODE"
    assert "hunter2" not in repr(report)
    assert "attacker.example" in (report.detail or "")


@pytest.mark.asyncio
async def test_local_only_audits_a_per_signal_remote_endpoint() -> None:
    env = {
        "MYRM_LOCAL_TRACE_ONLY": "1",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "https://metrics.corp.example/v1/metrics",
    }
    with patch.dict("os.environ", env):
        report = await TraceExportSecurityDiagnostic().check_health()
    assert report.code == "WARN_REMOTE_TRACE_IN_LOCAL_MODE"


@pytest.mark.asyncio
async def test_a_disabled_sdk_is_reported_as_no_export() -> None:
    env = {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317", "OTEL_SDK_DISABLED": "true"}
    with patch.dict("os.environ", env):
        report = await TraceExportSecurityDiagnostic().check_health()
    assert report.code == "OK_LOCAL_NOOP_ACTIVE"


@pytest.mark.asyncio
async def test_a_configured_endpoint_is_shown_without_credentials() -> None:
    with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://user:hunter2@collector.example:4318"}):
        report = await TraceExportSecurityDiagnostic().check_health()
    assert report.code == "OK_OTLP_EXPORT_ACTIVE"
    assert "hunter2" not in repr(report)
    assert "collector.example" in report.message


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
