"""Measured telemetry posture: what is configured, what is running and what actually left.

[INPUT]
- otlp.config (POS: requested endpoint / protocol / headers, local-isolation and kill-switch flags)
- otlp.stats::ExportStats (POS: measured export outcome from the privacy guard)
- gen_ai.content::capture_content_enabled (POS: content capture switch)

[OUTPUT]
- record_traces / record_traces_degraded / record_metrics / reset_traces / reset_metrics: runtime state writers
- build_posture: the posture document served to the settings card and SRE probes

[POS]
Every field is read from live state, never asserted: the provider/exporter that setup actually built,
the sampler the SDK is using, the export counters of the privacy guard, whether the metric pipeline
exists. Importable without the OpenTelemetry SDK so a bare install can still answer "disabled".
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from myrm_agent_harness.infra.tracing.gen_ai.content import capture_content_enabled
from myrm_agent_harness.infra.tracing.otlp.config import (
    DEFAULT_PROTOCOL,
    OtlpTarget,
    is_local_trace_only,
    parse_otlp_headers,
    redact_endpoint,
    resolve_target,
    sdk_disabled,
)
from myrm_agent_harness.infra.tracing.otlp.stats import ExportStats

EXPORTER_NONE = "none"
EXPORTER_OTLP_HTTP = "otlp_http"
EXPORTER_OTLP_GRPC = "otlp_grpc"
EXPORTER_CONSOLE = "console"

_COMMIT_DISPLAY_LENGTH = 7


@dataclass
class _TracesRuntime:
    target: OtlpTarget | None = None
    exporter_type: str = EXPORTER_NONE
    degraded_reason: str | None = None
    sampler: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    stats: Callable[[], ExportStats] | None = None


_lock = threading.Lock()
_traces = _TracesRuntime()
_metrics_exporting = False


def record_traces(
    *,
    target: OtlpTarget | None,
    exporter_type: str,
    sampler: str,
    git_branch: str | None,
    git_commit: str | None,
    stats: Callable[[], ExportStats],
) -> None:
    """Record the trace pipeline that setup actually built."""
    global _traces
    with _lock:
        _traces = _TracesRuntime(
            target=target,
            exporter_type=exporter_type,
            sampler=sampler,
            git_branch=git_branch,
            git_commit=git_commit[:_COMMIT_DISPLAY_LENGTH] if git_commit else None,
            stats=stats,
        )


def record_traces_degraded(*, target: OtlpTarget | None, reason: str) -> None:
    """Record that tracing was requested but the requested pipeline could not be built."""
    global _traces
    with _lock:
        _traces = _TracesRuntime(target=target, degraded_reason=reason)


def record_metrics(*, exporting: bool) -> None:
    global _metrics_exporting
    _metrics_exporting = exporting


def reset_traces() -> None:
    global _traces
    with _lock:
        _traces = _TracesRuntime()


def reset_metrics() -> None:
    record_metrics(exporting=False)


def _status(*, has_sdk: bool, initialized: bool, runtime: _TracesRuntime, stats: ExportStats | None) -> str:
    if not has_sdk:
        return "missing_sdk"
    if sdk_disabled():
        return "disabled"
    if initialized and runtime.exporter_type != EXPORTER_NONE:
        return "failing" if stats is not None and stats.last_export_failed else "active"
    if runtime.degraded_reason:
        return "degraded"
    if is_local_trace_only():
        return "local_only"
    return "noop"


def build_posture(*, initialized: bool, has_sdk: bool) -> dict[str, object]:
    """Assemble the posture document from live state."""
    with _lock:
        runtime = _traces
    stats = runtime.stats() if runtime.stats is not None else None
    target = runtime.target or resolve_target("traces")
    return {
        "status": _status(has_sdk=has_sdk, initialized=initialized, runtime=runtime, stats=stats),
        "initialized": initialized,
        "has_sdk": has_sdk,
        "endpoint": redact_endpoint(target.endpoint) if target else None,
        "protocol": target.protocol if target else DEFAULT_PROTOCOL,
        "headers_configured": target.headers_configured if target else bool(parse_otlp_headers()),
        "local_trace_only": is_local_trace_only(),
        "exporter_type": runtime.exporter_type,
        "degraded_reason": runtime.degraded_reason,
        "sampler": runtime.sampler,
        "content_capture": capture_content_enabled(),
        "metrics_exporting": _metrics_exporting,
        "exported_spans": stats.exported_spans if stats else 0,
        "failed_batches": stats.failed_batches if stats else 0,
        "dropped_spans": stats.dropped_spans if stats else 0,
        "last_success_at": stats.last_success_at if stats else None,
        "last_failure_at": stats.last_failure_at if stats else None,
        "git_branch": runtime.git_branch,
        "git_commit": runtime.git_commit,
    }
