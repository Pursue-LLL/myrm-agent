"""Webhook security middleware.

Provides protection against OOM attacks via payload size limits.

[INPUT]
- fastapi::Request, Response
- starlette.types::Message, Receive, Scope, Send

[OUTPUT]
- RawBodyLimitMiddleware: ASGI middleware for limiting raw body size

[POS]
Webhook 安全加固中间件。在反序列化 JSON 之前，强制校验请求体大小，
防止超大 Payload 导致单机沙箱 OOM 崩溃。
"""

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RawBodyLimitMiddleware:
    """Limits the raw body size of webhook requests to prevent OOM attacks.

    Only applies to paths starting with /api/channels/ to avoid interfering
    with other file upload endpoints.
    """

    def __init__(self, app: ASGIApp, max_size: int = 1024 * 1024) -> None:
        """Initialize middleware with a maximum body size (default 1MB)."""
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process ASGI request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Only limit channel webhook endpoints
        if not path.startswith("/api/channels/"):
            await self.app(scope, receive, send)
            return

        total_size = 0

        async def receive_with_limit() -> Message:
            nonlocal total_size
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                total_size += len(chunk)
                if total_size > self.max_size:
                    logger.warning("Webhook payload exceeded limit (%d bytes) on %s", self.max_size, path)
                    raise RuntimeError("Payload Too Large")
            return message

        try:
            await self.app(scope, receive_with_limit, send)
        except RuntimeError as e:
            if str(e) == "Payload Too Large":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"error": "Payload Too Large"}',
                    }
                )
            else:
                raise
