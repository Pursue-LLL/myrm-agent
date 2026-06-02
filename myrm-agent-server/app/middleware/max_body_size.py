"""
@input: 依赖 starlette.types 的 ASGI 相关类型
@output: 对外提供 MaxBodySizeMiddleware
@pos: ASGI 层的请求体大小限制中间件，防止 OOM 和磁盘耗尽攻击。

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import logging

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

class MaxBodySizeMiddleware:
    """
    ASGI Middleware to enforce a maximum request body size.
    
    This middleware wraps the `receive` callable to track the total bytes
    received. If the total exceeds `max_size`, it sends a 413 response
    and raises ClientDisconnect to abort the request parsing cleanly.
    """

    def __init__(self, app: ASGIApp, max_size: int):
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        total_size = 0
        response_started = False
        body_too_large = False

        async def receive_wrapper() -> Message:
            nonlocal total_size, body_too_large
            message = await receive()
            if message["type"] == "http.request":
                chunk_size = len(message.get("body", b""))
                total_size += chunk_size
                if total_size > self.max_size:
                    logger.warning(
                        f"Request body exceeded max size of {self.max_size} bytes. "
                        f"Client: {scope.get('client')}, Path: {scope.get('path')}"
                    )
                    body_too_large = True
                    if not response_started:
                        await self._send_413_response(send)
                    raise ClientDisconnect()
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if body_too_large:
                # We already sent the 413 response, ignore inner app's response
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except ClientDisconnect:
            # ClientDisconnect is expected when we abort the request
            pass

    async def _send_413_response(self, send: Send) -> None:
        """Send a 413 Payload Too Large response directly."""
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"connection", b"close"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b'{"detail": "Payload Too Large: Request body exceeds the maximum allowed size."}',
        })
