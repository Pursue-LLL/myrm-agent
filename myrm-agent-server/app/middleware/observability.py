"""Request tracing middleware.

Generates or adopts a ``trace_id`` per HTTP request and binds it (along with
``session_id`` from the URL path) into ``TracingContext`` so that all logs
emitted during request processing carry these identifiers automatically.

The id is the request's one identity: the ``X-Trace-Id`` response header, the
``error.trace_id`` of an error body, every log line and, because monitoring
installs the harness id generator, the trace id of the spans the request
starts. It is also kept on ``request.state`` for handlers that run after this
middleware has unwound (the unhandled-exception handler).

An inbound ``X-Trace-Id`` or W3C ``traceparent`` header is adopted to preserve
distributed trace continuity across reverse proxies, API gateways, and APM
systems, but only when it is a valid W3C trace id (32 hex digits, not all zero),
which is used in its lowercase form. Anything else, shorter hex ids included, is
replaced by a fresh UUID4-based id because OpenTelemetry cannot carry it.

Registered just before PublicIngress in the middleware stack so that the
trace context covers all inner middleware (auth, e2ee, sanitizer, etc.).

[INPUT]
- myrm_agent_harness.observability.tracing::TracingContext
  (POS: 请求级别 trace/session 上下文管理)
- myrm_agent_harness.infra.tracing::parse_trace_id
  (POS: 有效 W3C trace id 的唯一判定)

[OUTPUT]
- TracingMiddleware: 为每个 HTTP 请求注入 trace_id 和 session_id 到 TracingContext 与 request.state。
- request_trace_id: 读取中间件绑定在请求上的 trace_id（供中间件展开之后运行的异常处理器使用）。

[POS]
请求追踪中间件。在请求生命周期内绑定 trace_id/session_id 上下文，供日志、错误体、响应头与 span 共用。
支持入站 X-Trace-Id / traceparent 头传播，确保云托管部署场景下分布式链路不断裂。
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.infra.tracing import parse_trace_id
from myrm_agent_harness.observability.tracing import TracingContext
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_SESSION_PATH_PREFIX = "/api/sessions/"


def _canonical_trace_id(value: str | None) -> str | None:
    """Lowercase 32-digit form of a valid W3C trace id, else ``None``."""
    parsed = parse_trace_id(value)
    return None if parsed is None else format(parsed, "032x")


def _parse_inbound_trace_id(request: Request) -> str | None:
    """Extract a valid W3C trace id from inbound request headers.

    Priority: ``X-Trace-Id`` > ``traceparent`` (W3C Trace Context).
    Returns ``None`` when no valid trace id is found, so the caller falls back
    to generating a fresh one.  Accepting nothing but 32 hex digits also
    prevents log injection via crafted header values.
    """
    trace_id = _canonical_trace_id(request.headers.get("x-trace-id"))
    if trace_id is not None:
        return trace_id

    parts = (request.headers.get("traceparent") or "").split("-")
    return _canonical_trace_id(parts[1]) if len(parts) >= 3 else None


def request_trace_id(request: Request) -> str | None:
    """The trace id ``TracingMiddleware`` bound to ``request``, readable after the middleware has unwound."""
    trace_id: object = getattr(request.state, "trace_id", None)
    return trace_id if isinstance(trace_id, str) else None


def _extract_session_id(path: str) -> str:
    """Extract session_id from URL path like ``/api/sessions/<id>/...``."""
    if not path.startswith(_SESSION_PATH_PREFIX):
        return "-"
    rest = path[len(_SESSION_PATH_PREFIX) :]
    slash_idx = rest.find("/")
    return rest[:slash_idx] if slash_idx != -1 else rest


class TracingMiddleware(BaseHTTPMiddleware):
    """Injects trace_id and session_id into TracingContext per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = _parse_inbound_trace_id(request) or TracingContext.generate_trace_id()
        session_id = _extract_session_id(request.url.path)

        request.state.trace_id = trace_id
        trace_token = TracingContext.set_trace_id(trace_id)
        session_token = TracingContext.set_session_id(session_id)

        start = time.monotonic()
        try:
            response = await call_next(request)
            elapsed_ms = (time.monotonic() - start) * 1000
            response.headers["X-Trace-Id"] = trace_id
            logger.debug(
                "%s %s → %s (%.1fms) [trace=%s]",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                trace_id[:12],
            )
            return response
        except Exception:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.exception(
                "%s %s → 500 (%.1fms) [trace=%s]",
                request.method,
                request.url.path,
                elapsed_ms,
                trace_id[:12],
            )
            raise
        finally:
            TracingContext.reset_trace_id(trace_token)
            TracingContext.reset_session_id(session_token)
