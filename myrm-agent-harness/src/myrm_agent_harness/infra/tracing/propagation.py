"""Trace context propagation for distributed tracing.

Provides inject/extract utilities for propagating trace context across service boundaries, and the one
definition of a usable trace id that every inbound id is judged by.

[INPUT]
- opentelemetry.propagate (POS: Context propagation API)

[OUTPUT]
- inject_trace_context: 注入trace context
- extract_trace_context: 提取trace context
- parse_trace_id: a valid W3C trace id as the integer OpenTelemetry stores, else None

[POS]
Trace context propagation. Maintains complete trace chains across service calls.

"""

from __future__ import annotations

import re
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.context import Context

_TRACE_ID = re.compile(r"[0-9a-fA-F]{32}")


def inject_trace_context(carrier: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inject current trace context into carrier.

    Used when making outbound requests to propagate trace context.

    Args:
        carrier: Optional carrier dict to inject into (creates new if None)

    Returns:
        Carrier dict with injected trace context

    Example:
        headers = inject_trace_context()
        response = await http_client.post(url, headers=headers, ...)
    """
    if carrier is None:
        carrier = {}

    propagate.inject(carrier)
    return carrier


def extract_trace_context(carrier: dict[str, Any]) -> Context:
    """Extract trace context from carrier.

    Used when receiving inbound requests to continue trace from parent.

    Args:
        carrier: Carrier dict containing trace context (e.g., HTTP headers)

    Returns:
        OpenTelemetry context with extracted trace

    Example:
        context = extract_trace_context(request.headers)
        with tracer.start_as_current_span("handle_request", context=context):
            ...
    """
    return propagate.extract(carrier)


def get_current_trace_id() -> str | None:
    """Get current trace ID as hex string.

    Returns:
        Trace ID or None if no active span
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        trace_id = span.get_span_context().trace_id
        return format(trace_id, "032x")
    return None


def get_current_span_id() -> str | None:
    """Get current span ID as hex string.

    Returns:
        Span ID or None if no active span
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        span_id = span.get_span_context().span_id
        return format(span_id, "016x")
    return None


def parse_trace_id(value: str | None) -> int | None:
    """Parse a W3C trace id: exactly 32 hexadecimal digits that are not all zero.

    The one definition of a usable trace id, shared by whoever adopts an inbound id (``X-Trace-Id``,
    ``traceparent``) and by the id generator that turns it into the trace id of exported spans.

    Returns:
        The integer OpenTelemetry stores, or ``None`` when ``value`` is not a valid trace id.
        ``format(parsed, "032x")`` is its canonical lowercase form.
    """
    if value is None or _TRACE_ID.fullmatch(value) is None:
        return None
    parsed = int(value, 16)
    return parsed if parsed != 0 else None
