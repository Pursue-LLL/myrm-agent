"""Trace export policy and local-only isolation diagnostic probe.

[INPUT]
- myrm_agent_harness.infra.tracing::configured_endpoints, is_local_endpoint, is_local_trace_only, langsmith_tracing_requested, redact_endpoint, sdk_disabled (POS: the harness's single reading of the OTLP and LangSmith environment)

[OUTPUT]
- TraceExportSecurityDiagnostic: 诊断追踪是否处于安全本地隔离态，防止遥测与敏感数据意外远程外发

[POS]
Server infrastructure health diagnostics component. Each configured endpoint is judged by its parsed
host and shown redacted, exactly as the export path itself judges it. LangSmith's upload is a second
export path next to OTLP, so a switched-on LangSmith is reported in both modes.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.infra.tracing import (
    configured_endpoints,
    is_local_endpoint,
    is_local_trace_only,
    langsmith_tracing_requested,
    redact_endpoint,
    sdk_disabled,
)
from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)

logger = logging.getLogger(__name__)


class TraceExportSecurityDiagnostic(DiagnosticProtocol):
    """Probes OpenTelemetry export posture ensuring zero unauthorized egress."""

    async def check_health(self) -> HealthReport:
        try:
            endpoints = configured_endpoints()
            shown = redact_endpoint(endpoints[0]) if endpoints else "none"

            langsmith = langsmith_tracing_requested()

            if is_local_trace_only():
                if langsmith:
                    return HealthReport(
                        component_name="TraceExportSecurity",
                        status="warn",
                        code="WARN_LANGSMITH_IN_LOCAL_MODE",
                        message="Local-trace-only mode is active but LangSmith tracing is switched on (run inputs and outputs are uploaded).",
                        detail="LangSmith uploads through LangChain's own client, which the OTLP gate does not cover.",
                        fix_suggestion="Unset LANGSMITH_TRACING / LANGCHAIN_TRACING_V2, or restart so local-trace-only mode switches it off.",
                        meta_data={"local_only": True, "langsmith": True},
                    )
                remote = [redact_endpoint(endpoint) for endpoint in endpoints if not is_local_endpoint(endpoint)]
                if remote:
                    return HealthReport(
                        component_name="TraceExportSecurity",
                        status="warn",
                        code="WARN_REMOTE_TRACE_IN_LOCAL_MODE",
                        message="Local-trace-only mode is active but remote OTLP endpoint is configured (egress will be blocked).",
                        detail=f"Remote endpoint: {remote[0]}",
                        fix_suggestion="Unset OTEL_EXPORTER_OTLP_ENDPOINT or use a localhost collector endpoint.",
                        meta_data={"local_only": True, "otlp_endpoint": remote[0]},
                    )
                return HealthReport(
                    component_name="TraceExportSecurity",
                    status="pass",
                    code="OK_LOCAL_TRACE_ONLY_ENFORCED",
                    message="Trace export is strictly confined to local storage (zero remote egress).",
                    detail="MYRM_LOCAL_TRACE_ONLY is active. All trace and span events are retained locally.",
                    meta_data={"local_only": True, "otlp_endpoint": shown},
                )

            if langsmith:
                otlp_active = bool(endpoints) and not sdk_disabled()
                return HealthReport(
                    component_name="TraceExportSecurity",
                    status="pass",
                    code="OK_LANGSMITH_EXPORT_ACTIVE",
                    message="LangSmith tracing is enabled: the inputs and outputs of LLM runs are uploaded to LangSmith.",
                    detail=f"OTLP export is also configured to {shown}." if otlp_active else None,
                    meta_data={"local_only": False, "otlp_endpoint": shown, "langsmith": True},
                )

            if endpoints and not sdk_disabled():
                return HealthReport(
                    component_name="TraceExportSecurity",
                    status="pass",
                    code="OK_OTLP_EXPORT_ACTIVE",
                    message=f"OTLP export is configured to {shown}.",
                    meta_data={"local_only": False, "otlp_endpoint": shown},
                )

            return HealthReport(
                component_name="TraceExportSecurity",
                status="pass",
                code="OK_LOCAL_NOOP_ACTIVE",
                message="No OTLP export is enabled. Telemetry stays inside this process.",
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
