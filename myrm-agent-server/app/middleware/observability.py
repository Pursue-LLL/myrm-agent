"""Request tracing middleware.

Generates or adopts a ``trace_id`` per HTTP request and binds it (along with
``session_id`` from the URL path) into ``TracingContext`` so that all logs
emitted during request processing carry these identifiers automatically.

When an inbound ``X-Trace-Id`` or W3C ``traceparent`` header is present and
carries a valid hex trace-id, that value is adopted to preserve distributed
trace continuity across reverse proxies, API gateways, and APM systems.
Otherwise a fresh UUID4-based trace-id is generated.

Registered just before PublicIngress in the middleware stack so that the
trace context covers all inner middleware (auth, e2ee, sanitizer, etc.).

[INPUT]
- myrm_agent_harness.observability.tracing::TracingContext
  (POS: 请求级别 trace/session 上下文管理)

[OUTPUT]
- TracingMiddleware: 为每个 HTTP 请求注入 trace_id 和 session_id 到 TracingContext。

[POS]
请求追踪中间件。在请求生命周期内绑定 trace_id/session_id 上下文，供日志自动携带。
支持入站 X-Trace-Id / traceparent 头传播，确保云托管部署场景下分布式链路不断裂。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from myrm_agent_harness.observability.tracing import TracingContext
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_SESSION_PATH_PREFIX = "/api/sessions/"
_HEX_TRACE_RE = re.compile(r"[0-9a-fA-F]{1,64}")


def _parse_inbound_trace_id(request: Request) -> Optional[str]:
    """Extract a valid trace-id from inbound request headers.

    Priority: ``X-Trace-Id`` > ``traceparent`` (W3C Trace Context).
    Returns ``None`` when no valid hex trace-id is found, so the caller
    falls back to generating a fresh one.  Only 1-64 hex characters are
    accepted to prevent log injection via crafted header values.
    """
    raw = request.headers.get("x-trace-id")
    if raw and _HEX_TRACE_RE.fullmatch(raw):
        return raw

    traceparent = request.headers.get("traceparent")
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 3 and _HEX_TRACE_RE.fullmatch(parts[1]):
            return parts[1]

    return None


def _extract_session_id(path: str) -> str:
    """Extract session_id from URL path like ``/api/sessions/<id>/...``."""
    if not path.startswith(_SESSION_PATH_PREFIX):
        return "-"
    rest = path[len(_SESSION_PATH_PREFIX) :]
    slash_idx = rest.find("/")
    return rest[:slash_idx] if slash_idx != -1 else rest


class TracingMiddleware(BaseHTTPMiddleware):
    """Injects trace_id and session_id into TracingContext per request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        trace_id = _parse_inbound_trace_id(request) or TracingContext.generate_trace_id()
        session_id = _extract_session_id(request.url.path)

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
