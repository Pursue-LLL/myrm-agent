"""Tests for gateway zero-payload redacted health export and runtime diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.observability.diagnostics.gateway_health import (
    GatewayHealthInspector,
    GatewayHealthStatus,
    GatewayRedactedHealthDTO,
    GatewayVitals,
    OtlpHealth,
    check_gateway_runtime_health,
)


class TestGatewayHealthInspectorVitals:
    @pytest.mark.asyncio
    async def test_measure_event_loop_lag_non_negative(self) -> None:
        lag_ms = await GatewayHealthInspector.measure_event_loop_lag()
        assert lag_ms >= 0.0

    def test_get_process_rss_mb_uses_psutil_current_rss(self) -> None:
        memory_info = type("MemInfo", (), {"rss": 256 * 1024 * 1024})()
        with patch("myrm_agent_harness.observability.diagnostics.gateway_health.psutil") as mock_psutil:
            mock_psutil.Process.return_value.memory_info.return_value = memory_info
            rss_mb = GatewayHealthInspector.get_process_rss_mb()
        assert rss_mb == 256.0


class TestGatewayHealthInspectorOtlpPosture:
    @pytest.fixture(autouse=True)
    def _standard_otlp_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in (
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
            "OTEL_TRACES_EXPORTER",
            "OTEL_METRICS_EXPORTER",
            "OTEL_SDK_DISABLED",
        ):
            monkeypatch.delenv(name, raising=False)
        self._measured(monkeypatch, traces="noop", metrics="off")

    @staticmethod
    def _measured(monkeypatch: pytest.MonkeyPatch, *, traces: str, metrics: str) -> None:
        """Pin the measured state the doctor reads, so the process-global pipelines cannot leak in."""
        monkeypatch.setattr(
            "myrm_agent_harness.infra.tracing.get_telemetry_posture",
            lambda: {"status": traces, "metrics_status": metrics},
        )

    def test_otlp_not_configured_when_env_missing(self) -> None:
        health = GatewayHealthInspector.check_otlp_posture()
        assert health == OtlpHealth(configured=False, connected=False)

    def test_a_deliberately_disabled_sdk_is_not_reported_as_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        assert GatewayHealthInspector.check_otlp_posture().configured is False

    def test_both_signals_switched_off_is_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
        monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")
        assert GatewayHealthInspector.check_otlp_posture().configured is False

    def test_a_metrics_only_endpoint_counts_as_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://localhost:4318/v1/metrics")
        monkeypatch.setenv("OTEL_TRACES_EXPORTER", "none")
        assert GatewayHealthInspector.check_otlp_posture().configured is True

    @pytest.mark.parametrize(
        ("traces", "metrics"),
        [("active", "off"), ("ready", "active"), ("active", "active")],
    )
    def test_a_signal_whose_latest_export_was_accepted_is_connected(
        self, monkeypatch: pytest.MonkeyPatch, traces: str, metrics: str
    ) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        self._measured(monkeypatch, traces=traces, metrics=metrics)

        assert GatewayHealthInspector.check_otlp_posture() == OtlpHealth(configured=True, connected=True)

    @pytest.mark.parametrize(
        ("traces", "metrics"),
        [("ready", "ready"), ("ready", "off"), ("degraded", "off"), ("missing_sdk", "off"), ("local_only", "off")],
    )
    def test_a_pipeline_that_has_delivered_nothing_is_not_connected(
        self, monkeypatch: pytest.MonkeyPatch, traces: str, metrics: str
    ) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        self._measured(monkeypatch, traces=traces, metrics=metrics)

        assert GatewayHealthInspector.check_otlp_posture() == OtlpHealth(configured=True, connected=False)

    @pytest.mark.parametrize(
        ("traces", "metrics", "failing"),
        [
            ("failing", "off", ("traces",)),
            ("active", "failing", ("metrics",)),
            ("failing", "failing", ("traces", "metrics")),
        ],
    )
    def test_a_failing_signal_is_never_reported_connected(
        self, monkeypatch: pytest.MonkeyPatch, traces: str, metrics: str, failing: tuple[str, ...]
    ) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        self._measured(monkeypatch, traces=traces, metrics=metrics)

        assert GatewayHealthInspector.check_otlp_posture() == OtlpHealth(
            configured=True, connected=False, failing=failing
        )


class TestGatewayHealthInspectorInspect:
    @pytest.mark.asyncio
    async def test_healthy_when_vitals_nominal(self) -> None:
        vitals = GatewayVitals(
            event_loop_lag_ms=5.0,
            memory_rss_mb=256.0,
            uptime_seconds=120.0,
            active_tasks=4,
        )
        with (
            patch.object(GatewayHealthInspector, "collect_vitals", AsyncMock(return_value=vitals)),
            patch.object(GatewayHealthInspector, "check_otlp_posture", return_value=OtlpHealth(False, False)),
        ):
            dto = await GatewayHealthInspector.inspect()

        assert dto.status == GatewayHealthStatus.HEALTHY
        assert dto.vitals.active_tasks == 4
        assert "operating nominally" in dto.redacted_diagnostics[0]

    @pytest.mark.asyncio
    async def test_unhealthy_on_critical_event_loop_lag(self) -> None:
        vitals = GatewayVitals(
            event_loop_lag_ms=1500.0,
            memory_rss_mb=256.0,
            uptime_seconds=120.0,
            active_tasks=2,
        )
        with (
            patch.object(GatewayHealthInspector, "collect_vitals", AsyncMock(return_value=vitals)),
            patch.object(GatewayHealthInspector, "check_otlp_posture", return_value=OtlpHealth(False, False)),
        ):
            dto = await GatewayHealthInspector.inspect()

        assert dto.status == GatewayHealthStatus.UNHEALTHY
        assert any("event loop lag" in note.lower() for note in dto.redacted_diagnostics)

    @pytest.mark.asyncio
    async def test_degraded_on_memory_warn_threshold(self) -> None:
        vitals = GatewayVitals(
            event_loop_lag_ms=5.0,
            memory_rss_mb=GatewayHealthInspector.MEMORY_WARN_MB + 10.0,
            uptime_seconds=120.0,
            active_tasks=2,
        )
        with (
            patch.object(GatewayHealthInspector, "collect_vitals", AsyncMock(return_value=vitals)),
            patch.object(GatewayHealthInspector, "check_otlp_posture", return_value=OtlpHealth(False, False)),
        ):
            dto = await GatewayHealthInspector.inspect()

        assert dto.status == GatewayHealthStatus.DEGRADED
        assert any("RSS memory elevated" in note for note in dto.redacted_diagnostics)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("health", "note"),
        [
            (OtlpHealth(True, False, ("traces",)), "OTLP traces export is failing"),
            (OtlpHealth(True, False, ("traces", "metrics")), "OTLP traces and metrics export is failing"),
            (OtlpHealth(True, False), "no export has been accepted yet"),
        ],
    )
    async def test_an_otlp_problem_is_named_in_the_diagnostics_without_changing_the_status(
        self, health: OtlpHealth, note: str
    ) -> None:
        vitals = GatewayVitals(event_loop_lag_ms=5.0, memory_rss_mb=256.0, uptime_seconds=120.0, active_tasks=4)
        with (
            patch.object(GatewayHealthInspector, "collect_vitals", AsyncMock(return_value=vitals)),
            patch.object(GatewayHealthInspector, "check_otlp_posture", return_value=health),
        ):
            dto = await GatewayHealthInspector.inspect()

        assert dto.status == GatewayHealthStatus.HEALTHY
        assert any(note in line for line in dto.redacted_diagnostics)
        assert (dto.otlp_endpoint_configured, dto.otlp_connected) == (True, False)

    @pytest.mark.asyncio
    async def test_a_connected_destination_adds_no_otlp_note(self) -> None:
        vitals = GatewayVitals(event_loop_lag_ms=5.0, memory_rss_mb=256.0, uptime_seconds=120.0, active_tasks=4)
        with (
            patch.object(GatewayHealthInspector, "collect_vitals", AsyncMock(return_value=vitals)),
            patch.object(GatewayHealthInspector, "check_otlp_posture", return_value=OtlpHealth(True, True)),
        ):
            dto = await GatewayHealthInspector.inspect()

        assert not any("OTLP" in line for line in dto.redacted_diagnostics)
        assert dto.otlp_connected is True

    @pytest.mark.asyncio
    async def test_dto_to_dict_excludes_sensitive_fields(self) -> None:
        dto = GatewayRedactedHealthDTO(
            status=GatewayHealthStatus.HEALTHY,
            vitals=GatewayVitals(1.0, 100.0, 60.0, 1),
            otlp_endpoint_configured=False,
            otlp_connected=False,
            redacted_diagnostics=("Gateway vitals nominal.",),
        )
        payload = dto.to_dict()
        assert set(payload.keys()) == {
            "status",
            "vitals",
            "otlp_endpoint_configured",
            "otlp_connected",
            "redacted_diagnostics",
        }
        assert "prompt" not in str(payload).lower()


class TestCheckGatewayRuntimeHealthProbe:
    @pytest.mark.asyncio
    async def test_probe_uses_health_report_contract(self) -> None:
        dto = GatewayRedactedHealthDTO(
            status=GatewayHealthStatus.DEGRADED,
            vitals=GatewayVitals(250.0, 512.0, 300.0, 8),
            otlp_endpoint_configured=True,
            otlp_connected=False,
            redacted_diagnostics=("Elevated event loop lag.",),
        )
        with patch.object(GatewayHealthInspector, "inspect", AsyncMock(return_value=dto)):
            report = await check_gateway_runtime_health()

        assert report.component_name == "GatewayRuntime"
        assert report.status == "warn"
        assert "Gateway Runtime" in report.message
        assert report.fix_suggestion


class TestGatewayHealthRegistration:
    def test_probe_registered_in_diagnostic_manager(self) -> None:
        import myrm_agent_harness.observability.diagnostics.manager as manager_module

        hook_names = [getattr(hook, "__name__", "") for hook in manager_module._diagnostic_hooks]
        assert "check_gateway_runtime_health" in hook_names
