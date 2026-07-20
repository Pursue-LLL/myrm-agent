"""Request tracing middleware.

Generates a unique ``trace_id`` per HTTP request and binds it (along with
``session_id`` from the URL path) into ``TracingContext`` so that all logs
emitted during request processing carry these identifiers automatically.

Registered just before PublicIngress in the middleware stack so that the
trace context covers all inner middleware (auth, e2ee, sanitizer, etc.).

[INPUT]
- myrm_agent_harness.observability.tracing::TracingContext
  (POS: 请求级别 trace/session 上下文管理)

[OUTPUT]
- TracingMiddleware: 为每个 HTTP 请求注入 trace_id 和 session_id 到 TracingContext。

[POS]
请求追踪中间件。在请求生命周期内绑定 trace_id/session_id 上下文，供日志自动携带。
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.observability.tracing import TracingContext
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_SESSION_PATH_PREFIX = "/api/sessions/"


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
        trace_id = TracingContext.generate_trace_id()
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
