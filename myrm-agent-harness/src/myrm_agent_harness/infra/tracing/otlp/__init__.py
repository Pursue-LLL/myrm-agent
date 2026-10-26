"""OTLP export plumbing: target resolution, exporters, privacy guard and measured posture.

[INPUT]
- otlp.config / otlp.posture / otlp.stats (POS: SDK-free configuration and posture state)
- otlp.exporters / otlp.privacy / otlp.resource / otlp.lifecycle (POS: SDK-bound pieces, imported on demand)

[OUTPUT]
- Configuration: OtlpTarget, resolve_target, configured_endpoints, parse_otlp_headers, protocol names, local-isolation checks
- Posture: build_posture and the runtime state writers

[POS]
The facade carries only what works without the OpenTelemetry SDK. Anything that needs the SDK or an
exporter package lives in its own module and is imported by ``setup_tracing`` / ``setup_metrics``
when they actually build a pipeline, so a bare install keeps importing cleanly.
"""

from myrm_agent_harness.infra.tracing.otlp.config import (
    DEFAULT_PROTOCOL,
    PROTOCOL_GRPC,
    PROTOCOL_HTTP,
    OtlpTarget,
    apply_local_isolation,
    assert_local_trace_only,
    configured_endpoints,
    is_local_endpoint,
    is_local_trace_only,
    parse_otlp_headers,
    redact_endpoint,
    resolve_target,
    sdk_disabled,
)
from myrm_agent_harness.infra.tracing.otlp.posture import build_posture
from myrm_agent_harness.infra.tracing.otlp.stats import ExportStats

__all__ = [
    "DEFAULT_PROTOCOL",
    "PROTOCOL_GRPC",
    "PROTOCOL_HTTP",
    "ExportStats",
    "OtlpTarget",
    "apply_local_isolation",
    "assert_local_trace_only",
    "build_posture",
    "configured_endpoints",
    "is_local_endpoint",
    "is_local_trace_only",
    "parse_otlp_headers",
    "redact_endpoint",
    "resolve_target",
    "sdk_disabled",
]
