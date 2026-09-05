"""Trace export policy and local-only isolation diagnostic probe.

[INPUT]
- myrm_agent_harness.infra.tracing::is_local_trace_only (POS: 本地追踪门禁判定)

[OUTPUT]
- TraceExportSecurityDiagnostic: 诊断追踪是否处于安全本地隔离态，防止遥测与敏感数据意外远程外发

[POS]
Server infrastructure health diagnostics component.
"""

from __future__ import annotations

import logging
import os

from myrm_agent_harness.infra.tracing import is_local_trace_only
from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)

logger = logging.getLogger(__name__)


class TraceExportSecurityDiagnostic(DiagnosticProtocol):
    """Probes OpenTelemetry trace exporter posture ensuring zero unauthorized egress."""

    async def check_health(self) -> HealthReport:
        try:
            otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
            local_only = is_local_trace_only()

            if local_only:
                if otlp_endpoint and not (
                    otlp_endpoint.startswith(("http://localhost", "http://127.0.0.1", "grpc://localhost", "grpc://127.0.0.1"))
                ):
                    return HealthReport(
                        component_name="TraceExportSecurity",
                        status="warn",
                        code="WARN_REMOTE_TRACE_IN_LOCAL_MODE",
                        message="Local-trace-only mode is active but remote OTLP endpoint is configured (egress will be blocked).",
                        detail=f"Remote endpoint: {otlp_endpoint}",
                        fix_suggestion="Unset OTEL_EXPORTER_OTLP_ENDPOINT or use a localhost collector endpoint.",
                        meta_data={"local_only": True, "otlp_endpoint": otlp_endpoint},
                    )
                return HealthReport(
                    component_name="TraceExportSecurity",
                    status="pass",
                    code="OK_LOCAL_TRACE_ONLY_ENFORCED",
                    message="Trace export is strictly confined to local storage (zero remote egress).",
                    detail="MYRM_LOCAL_TRACE_ONLY is active. All trace and span events are retained locally.",
                    meta_data={"local_only": True, "otlp_endpoint": otlp_endpoint or "none"},
                )

            # Normal mode
            if otlp_endpoint:
                return HealthReport(
                    component_name="TraceExportSecurity",
                    status="pass",
                    code="OK_OTLP_EXPORT_ACTIVE",
                    message=f"OTLP trace export active to {otlp_endpoint}.",
                    meta_data={"local_only": False, "otlp_endpoint": otlp_endpoint},
                )

            return HealthReport(
                component_name="TraceExportSecurity",
                status="pass",
                code="OK_LOCAL_NOOP_ACTIVE",
                message="No remote OTLP endpoint configured. Tracing operates in local/NoOp mode.",
                meta_data={"local_only": False, "otlp_endpoint": "none"},
            )
        except Exception as exc:
            logger.warning("TraceExportSecurity check failed: %s", exc)
            return HealthReport(
                component_name="TraceExportSecurity",
                status="warn",
                code="WARN_TRACE_SECURITY_DEGRADED",
                message="Failed to audit trace export security posture.",
                detail=str(exc),
            )
