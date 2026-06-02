"""
Client-side error logging endpoint.

Receives frontend crash reports from GlobalErrorBoundary and logs them
server-side for production monitoring.  Rate-limited to prevent abuse.
"""

import logging
import time
from collections import deque

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])

_WINDOW_SECS = 60
_MAX_PER_WINDOW = 30
_recent_ts: deque[float] = deque(maxlen=_MAX_PER_WINDOW)


class ClientErrorReport(BaseModel):
    error: str = Field(max_length=2000)
    stack: str | None = Field(default=None, max_length=10000)
    componentStack: str | None = Field(default=None, max_length=10000)
    userAgent: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    timestamp: str | None = None


@router.post("/client-error", status_code=status.HTTP_204_NO_CONTENT)
async def receive_client_error(
    report: ClientErrorReport, request: Request
) -> Response:
    now = time.monotonic()
    while _recent_ts and now - _recent_ts[0] > _WINDOW_SECS:
        _recent_ts.popleft()
    if len(_recent_ts) >= _MAX_PER_WINDOW:
        return Response(status_code=status.HTTP_429_TOO_MANY_REQUESTS)
    _recent_ts.append(now)

    client_ip = request.client.host if request.client else "unknown"
    logger.warning(
        "Client render error from %s | url=%s | ua=%s | error=%s",
        client_ip,
        report.url or "unknown",
        (report.userAgent or "unknown")[:80],
        report.error[:500],
    )
    if report.stack:
        logger.debug("Client error stack:\n%s", report.stack[:3000])
    if report.componentStack:
        logger.debug("Component stack:\n%s", report.componentStack[:3000])

    return Response(status_code=status.HTTP_204_NO_CONTENT)
