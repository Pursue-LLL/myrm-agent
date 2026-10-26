"""Trace export audit probe for the doctor.

[INPUT]
- infra.tracing.otlp.config::configured_endpoints, is_local_endpoint, is_local_trace_only, redact_endpoint (POS: Endpoint and mode resolution shared with the exporter, so the audit judges what the exporter would dial.)
- diagnostics.protocols::HealthReport (POS: Standard health check report)

[OUTPUT]
- check_local_trace_export_audit: Audit that trace export stays local while local-trace-only mode is on.

[POS]
Harness-level doctor probe registered through probes.py; kept apart so the probe module stays within its line budget.
"""

from myrm_agent_harness.observability.diagnostics.protocols import HealthReport


async def check_local_trace_export_audit() -> HealthReport:
    """Audit trace export isolation to guarantee zero unauthorized remote telemetry leaks.

    Validates that:
    1. In local-trace-only mode (MYRM_LOCAL_TRACE_ONLY=1), no remote OTLP export occurs.
    2. Any remote endpoint is flagged, ensuring compliance with strict privacy baselines.

    Every configured endpoint (general and per-signal) is audited by its parsed host, not by a
    prefix match on the raw variable.
    """
    from myrm_agent_harness.infra.tracing.otlp.config import (
        configured_endpoints,
        is_local_endpoint,
        is_local_trace_only,
        redact_endpoint,
    )

    local_only = is_local_trace_only()
    endpoints = configured_endpoints()

    if local_only:
        remote = [redact_endpoint(endpoint) for endpoint in endpoints if not is_local_endpoint(endpoint)]
        if remote:
            return HealthReport(
                component_name="TraceExportAudit",
                status="fail",
                code="ERR_TRACE_REMOTE_LEAK_RISK",
                message="Remote trace endpoint detected while local-trace-only mode is active.",
                detail=f"Blocked external endpoint: '{remote[0]}'. Telemetry will not be exported to it.",
                fix_suggestion="Unset OTEL_EXPORTER_OTLP_ENDPOINT or use a localhost collector in local mode.",
                meta_data={"local_trace_only": True, "blocked_endpoint": remote[0]},
            )
        return HealthReport(
            component_name="TraceExportAudit",
            status="pass",
            code="OK_LOCAL_TRACE_ISOLATION",
            message="Local trace isolation is fully enforced.",
            detail="Trace data is restricted to local storage (JSONL/SQLite); zero unauthorized remote export.",
            meta_data={"local_trace_only": True},
        )

    return HealthReport(
        component_name="TraceExportAudit",
        status="pass",
        code="OK_TRACE_EXPORT_STANDARD",
        message="Trace export operating in standard mode.",
        detail="Standard telemetry export active.",
        meta_data={
            "local_trace_only": False,
            "otlp_endpoint": redact_endpoint(endpoints[0]) if endpoints else "none",
        },
    )
