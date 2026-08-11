"""Loopback HTTP/WebSocket server exposing a Chrome DevTools endpoint for Playwright.

[INPUT]
- cdp_relay.bridge::ExtensionCdpRelayBridge (POS: CDP relay bridge)
- aiohttp::web (POS: loopback HTTP/WebSocket server)

[OUTPUT]
- LoopbackCdpRelayServer: serves /json/* and /cdp on 127.0.0.1

[POS]
Loopback DevTools façade so Playwright connect_over_cdp needs no code changes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiohttp import WSMsgType, web

if TYPE_CHECKING:
    from .bridge import ExtensionCdpRelayBridge

logger = logging.getLogger(__name__)


class LoopbackCdpRelayServer:
    """Serves /json/version and /cdp WebSocket on 127.0.0.1 only."""

    def __init__(self, bridge: ExtensionCdpRelayBridge) -> None:
        self._bridge = bridge
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._port: int = 0

    @property
    def http_endpoint(self) -> str | None:
        if self._port <= 0:
            return None
        return f"http://127.0.0.1:{self._port}"

    @property
    def is_running(self) -> bool:
        return self._port > 0 and self._runner is not None

    async def start(self) -> str:
        if self.is_running and self.http_endpoint:
            return self.http_endpoint

        app = web.Application()
        app.router.add_get("/json/version", self._handle_json_version)
        app.router.add_get("/json/list", self._handle_json_list)
        app.router.add_get("/json", self._handle_json_list)
        app.router.add_get("/cdp", self._handle_cdp_ws)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host="127.0.0.1", port=0)
        await self._site.start()

        server = self._site._server  # noqa: SLF001 — aiohttp internal for dynamic port
        if server is None or not server.sockets:
            raise RuntimeError("Failed to bind loopback CDP relay server")
        self._port = int(server.sockets[0].getsockname()[1])
        endpoint = self.http_endpoint
        if endpoint is None:
            raise RuntimeError("Loopback CDP relay server started without endpoint")
        logger.info("Extension CDP relay listening at %s", endpoint)
        return endpoint

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None
        self._port = 0

    def _loopback_guard(self, request: web.Request) -> bool:
        host = (request.host or "").split(":")[0].lower()
        return host in {"127.0.0.1", "localhost", "::1", "[::1]"}

    async def _handle_json_version(self, request: web.Request) -> web.Response:
        if not self._loopback_guard(request):
            raise web.HTTPForbidden(text="Forbidden")
        identity = self._bridge.identity
        ws_url = f"ws://127.0.0.1:{self._port}/cdp"
        payload = {
            "Browser": identity.browser_version or "Chrome/unknown",
            "Protocol-Version": "1.3",
            "User-Agent": identity.user_agent or "unknown",
            "webSocketDebuggerUrl": ws_url,
        }
        return web.json_response(payload)

    async def _handle_json_list(self, request: web.Request) -> web.Response:
        if not self._loopback_guard(request):
            raise web.HTTPForbidden(text="Forbidden")
        ws_url = f"ws://127.0.0.1:{self._port}/cdp"
        payload = [
            {
                "description": "Myrm extension relay",
                "devtoolsFrontendUrl": ws_url,
                "id": "myrm-relay-page",
                "title": "Myrm Extension Relay",
                "type": "page",
                "url": "about:blank",
                "webSocketDebuggerUrl": ws_url,
            }
        ]
        return web.json_response(payload)

    async def _handle_cdp_ws(self, request: web.Request) -> web.WebSocketResponse:
        if not self._loopback_guard(request):
            raise web.HTTPForbidden(text="Forbidden")

        ws = web.WebSocketResponse(autoping=True, heartbeat=30.0)
        await ws.prepare(request)

        def send(raw: str) -> None:
            if not ws.closed:
                asyncio.create_task(ws.send_str(raw))

        on_message, on_close = self._bridge.attach_cdp_client(send)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    on_message(msg.data)
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
        finally:
            on_close()
        return ws
