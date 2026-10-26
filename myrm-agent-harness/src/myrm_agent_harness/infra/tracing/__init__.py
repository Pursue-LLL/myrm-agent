"""Distributed tracing and metrics with OpenTelemetry.

Provides call chain tracing and metrics collection for observability.

Design: The framework provides consumer APIs (get_tracer, get_meter, trace_async,
trace_context) that work with OpenTelemetry's default NoOp provider when no
TracerProvider/MeterProvider is configured — zero overhead by default.

Initialization functions (setup_tracing, setup_metrics) are convenience helpers
intended for the business layer. The framework never calls them automatically.
GenAI spans (invoke_agent / chat / execute_tool) live in the ``gen_ai`` subpackage; the OTLP
pipeline (endpoint resolution, exporters, privacy guard, measured posture) in ``otlp``.

[INPUT]
- opentelemetry-api (POS: 追踪API)
- opentelemetry-sdk (POS: 追踪SDK)

[OUTPUT]
- setup_tracing: 初始化追踪（业务层调用）
- setup_metrics: 初始化 Metrics 导出（业务层调用）
- get_tracer: 获取追踪器（框架内部使用）
- get_meter: 获取 Meter 实例（框架内部使用）
- trace_async: 异步函数追踪装饰器（框架内部使用）
- is_tracing_initialized / is_metrics_initialized: 实测初始化状态
- get_telemetry_posture: 实测遥测态势
- configured_endpoints / is_local_endpoint / redact_endpoint / sdk_disabled: 标准 OTLP 环境变量读数（业务层诊断与探针共用同一份判定）

[POS]
Distributed tracing and metrics collection. Integrates OpenTelemetry for call chain tracing, performance analysis, and metrics export.

"""

from .metrics import (
    DynamicLabelManager,
    force_flush_metrics,
    get_meter,
    get_meter_provider,
    is_metrics_initialized,
    sanitize_metric_labels,
    setup_metrics,
    shutdown_metrics,
)
from .otlp import (
    configured_endpoints,
    is_local_endpoint,
    redact_endpoint,
    sdk_disabled,
)
from .propagation import (
    extract_trace_context,
    get_current_span_id,
    get_current_trace_id,
    inject_trace_context,
)
from .sanitizer import (
    TraceSpanSanitizer,
    sanitize_trace_attributes,
    sanitize_trace_payload,
)
from .tracer import (
    assert_local_trace_only,
    flush_observability,
    force_flush_tracing,
    get_telemetry_posture,
    get_tracer,
    is_local_trace_only,
    is_tracing_initialized,
    parse_otlp_headers,
    setup_tracing,
    shutdown_observability,
    shutdown_tracing,
    trace_async,
    trace_context,
)

__all__ = [
    "DynamicLabelManager",
    "TraceSpanSanitizer",
    "assert_local_trace_only",
    "configured_endpoints",
    "extract_trace_context",
    "flush_observability",
    "force_flush_metrics",
    "force_flush_tracing",
    "get_current_span_id",
    "get_current_trace_id",
    "get_meter",
    "get_meter_provider",
    "get_telemetry_posture",
    "get_tracer",
    "inject_trace_context",
    "is_local_endpoint",
    "is_local_trace_only",
    "is_metrics_initialized",
    "is_tracing_initialized",
    "parse_otlp_headers",
    "redact_endpoint",
    "sanitize_metric_labels",
    "sanitize_trace_attributes",
    "sanitize_trace_payload",
    "sdk_disabled",
    "setup_metrics",
    "setup_tracing",
    "shutdown_metrics",
    "shutdown_observability",
    "shutdown_tracing",
    "trace_async",
    "trace_context",
]
