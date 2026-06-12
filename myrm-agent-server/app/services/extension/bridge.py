"""Extension Bridge Service — business-layer implementation.

[INPUT]
- fastapi::WebSocket (POS: WebSocket connection from browser extension)
- myrm_agent_harness.toolkits.browser.pool.extension_bridge::ExtensionBridge (POS: Protocol contract)
- myrm_agent_harness.toolkits.browser.pool.extension_bridge::ExtensionTab, ExtensionStatus
- myrm_agent_harness.toolkits.browser.pool.browser_launcher::BrowserInstance

[OUTPUT]
- ExtensionBridgeService: Singleton managing extension WebSocket connection and CDP routing

[POS]
Business layer bridge connecting the browser extension (MV3 WebSocket) to the harness
BrowserLauncher. Implements the ExtensionBridge Protocol defined in the harness layer.
Handles: connection lifecycle, heartbeat, domain authorization, tab listing, and CDP proxy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from myrm_agent_harness.toolkits.browser.pool.browser_launcher import BrowserInstance

try:
    from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
        ExtensionBridgeNotAvailable,
        ExtensionStatus,
        ExtensionTab,
    )
except ImportError:
    from dataclasses import dataclass, field

    class ExtensionBridgeNotAvailable(Exception):
        pass

    @dataclass
    class ExtensionTab:
        tab_id: int = 0
        url: str = ""
        title: str = ""
        active: bool = False

    @dataclass
    class ExtensionStatus:
        connected: bool = False
        authorized_domains: list[str] = field(default_factory=list)
        tabs: list[ExtensionTab] = field(default_factory=list)
        version: str = ""

if TYPE_CHECKING:
    from patchright.async_api import Browser, Playwright

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 15.0
_HEARTBEAT_TIMEOUT = 30.0


class ExtensionBridgeService:
    """Manages the WebSocket connection to the browser extension.

    Singleton per server instance (one user = one extension connection in sandbox model).
    Implements the ExtensionBridge Protocol for harness integration.
    """

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._connected = False
        self._extension_version = ""
        self._browser_name = ""
        self._authorized_domains: list[str] = []
        self._tabs: list[ExtensionTab] = []
        self._last_heartbeat: float = 0.0
        self._pending_requests: dict[str, asyncio.Future[object]] = {}
        self._request_counter = 0
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._cdp_endpoint: str | None = None
        self._lock = asyncio.Lock()
        self._playwright: Playwright | None = None

    # --- Protocol Implementation (ExtensionBridge) ---

    async def _ensure_playwright(self) -> Playwright:
        """Return the cached Playwright instance, starting one if needed."""
        if self._playwright is None:
            from patchright.async_api import async_playwright

            self._playwright = await async_playwright().start()
        return self._playwright

    @staticmethod
    def _match_domain(domain: str, patterns: list[str]) -> bool:
        """Check if *domain* matches any pattern in *patterns*.

        Supports wildcard prefixes: ``*.example.com`` matches ``sub.example.com``
        and ``deep.sub.example.com`` but not ``example.com`` itself.
        """
        from fnmatch import fnmatch

        domain_lower = domain.lower()
        for pattern in patterns:
            p = pattern.lower()
            if p == domain_lower:
                return True
            if p.startswith("*.") and fnmatch(domain_lower, p):
                return True
        return False

    async def connect(self, *, timeout: float = 10.0) -> BrowserInstance:
        if not self._connected or self._ws is None:
            raise ExtensionBridgeNotAvailable(
                "Browser extension is not connected. Please install and connect the extension."
            )

        cdp_ws_url = await self._request_cdp_target(timeout=timeout)
        pw = await self._ensure_playwright()
        browser = await pw.chromium.connect_over_cdp(cdp_ws_url, timeout=timeout * 1000)

        return BrowserInstance(
            browser=browser,
            engine="chromium-patchright",
            is_managed=False,
            _pid=None,
        )

    async def connect_to_domain(self, domain: str, *, timeout: float = 10.0) -> BrowserInstance:
        if not self._match_domain(domain, self._authorized_domains):
            raise ExtensionBridgeNotAvailable(
                f"Domain '{domain}' is not authorized. "
                f"Authorized domains: {self._authorized_domains}"
            )

        if not self._connected or self._ws is None:
            raise ExtensionBridgeNotAvailable("Browser extension is not connected.")

        cdp_ws_url = await self._request_cdp_target(domain=domain, timeout=timeout)
        pw = await self._ensure_playwright()
        browser = await pw.chromium.connect_over_cdp(cdp_ws_url, timeout=timeout * 1000)

        return BrowserInstance(
            browser=browser,
            engine="chromium-patchright",
            is_managed=False,
            _pid=None,
        )

    async def get_status(self) -> ExtensionStatus:
        return ExtensionStatus(
            connected=self._connected,
            extension_version=self._extension_version,
            browser_name=self._browser_name,
            authorized_domains=list(self._authorized_domains),
            available_tabs=list(self._tabs),
            last_heartbeat_at=self._last_heartbeat,
        )

    def is_connected(self) -> bool:
        return self._connected

    async def list_tabs(self) -> list[ExtensionTab]:
        if not self._connected:
            return []
        await self._refresh_tabs()
        return [t for t in self._tabs if self._match_domain(t.domain, self._authorized_domains)]

    async def disconnect(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self._ws and self._ws.client_state == WebSocketState.CONNECTED:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._connected = False
        self._ws = None
        self._tabs = []
        logger.info("Extension bridge disconnected")

    # --- WebSocket Session Management ---

    async def handle_ws_connection(self, ws: WebSocket) -> None:
        """Handle incoming WebSocket connection from the browser extension."""
        await ws.accept()

        async with self._lock:
            if self._ws is not None:
                await self.disconnect()
            self._ws = ws
            self._connected = True
            self._last_heartbeat = time.monotonic()

        logger.info("Extension bridge connected")

        self._receive_task = asyncio.create_task(self._receive_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            await self._receive_task
        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            self._ws = None
            for fut in self._pending_requests.values():
                if not fut.done():
                    fut.set_exception(ExtensionBridgeNotAvailable("Connection lost"))
            self._pending_requests.clear()
            logger.info("Extension bridge WebSocket closed")

    async def _receive_loop(self) -> None:
        """Main receive loop for extension WebSocket messages."""
        assert self._ws is not None
        try:
            while True:
                raw = await self._ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "pong":
                    self._last_heartbeat = time.monotonic()

                elif msg_type == "hello":
                    self._extension_version = msg.get("version", "")
                    self._browser_name = msg.get("browser", "")
                    logger.info(
                        "Extension hello: %s on %s",
                        self._extension_version,
                        self._browser_name,
                    )

                elif msg_type == "tabs_update":
                    self._tabs = [
                        ExtensionTab(
                            tab_id=t["id"],
                            url=t["url"],
                            title=t.get("title", ""),
                            domain=t.get("domain", ""),
                            active=t.get("active", False),
                        )
                        for t in msg.get("tabs", [])
                    ]

                elif msg_type == "response":
                    req_id = msg.get("id", "")
                    if req_id in self._pending_requests:
                        fut = self._pending_requests.pop(req_id)
                        if msg.get("error"):
                            fut.set_exception(
                                ExtensionBridgeNotAvailable(msg["error"])
                            )
                        else:
                            fut.set_result(msg.get("data"))

                elif msg_type == "domains_update":
                    self._authorized_domains = msg.get("domains", [])

        except WebSocketDisconnect:
            logger.info("Extension disconnected by client")
        except Exception as exc:
            logger.warning("Extension receive error: %s", exc)

    async def _heartbeat_loop(self) -> None:
        """Send periodic pings and detect stale connections."""
        try:
            while self._connected and self._ws:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                if not self._connected or not self._ws:
                    break

                elapsed = time.monotonic() - self._last_heartbeat
                if elapsed > _HEARTBEAT_TIMEOUT:
                    logger.warning("Extension heartbeat timeout (%.1fs), disconnecting", elapsed)
                    await self.disconnect()
                    break

                try:
                    await self._ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    # --- Internal Helpers ---

    async def _send_request(self, action: str, payload: dict[str, object] | None = None, *, timeout: float = 10.0) -> object:
        """Send a request to the extension and wait for response."""
        if not self._connected or not self._ws:
            raise ExtensionBridgeNotAvailable("Extension not connected")

        self._request_counter += 1
        req_id = f"req_{self._request_counter}"

        msg: dict[str, object] = {"type": "request", "id": req_id, "action": action}
        if payload:
            msg["payload"] = payload

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[object] = loop.create_future()
        self._pending_requests[req_id] = fut

        try:
            await self._ws.send_text(json.dumps(msg))
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise ExtensionBridgeNotAvailable(f"Extension request '{action}' timed out")

    async def _request_cdp_target(
        self,
        domain: str | None = None,
        tab_id: int | None = None,
        *,
        timeout: float = 10.0,
    ) -> str:
        """Request the extension to attach debugger and return CDP WebSocket URL.

        When *tab_id* is provided the extension attaches directly to that tab,
        bypassing domain-based tab selection.  This enables precise tab targeting
        when the caller already knows which tab to control.
        """
        payload: dict[str, object] = {}
        if tab_id is not None:
            payload["tabId"] = tab_id
        elif domain:
            payload["domain"] = domain

        result = await self._send_request("attach_debugger", payload, timeout=timeout)
        cdp_ws_url = result.get("cdp_ws_url") if isinstance(result, dict) else None
        if not cdp_ws_url:
            raise ExtensionBridgeNotAvailable("Extension did not return CDP WebSocket URL")
        return cdp_ws_url

    async def _refresh_tabs(self) -> None:
        """Request fresh tab list from extension."""
        try:
            result = await self._send_request("list_tabs", timeout=5.0)
            if isinstance(result, list):
                self._tabs = [
                    ExtensionTab(
                        tab_id=t["id"],
                        url=t["url"],
                        title=t.get("title", ""),
                        domain=t.get("domain", ""),
                        active=t.get("active", False),
                    )
                    for t in result
                ]
        except ExtensionBridgeNotAvailable:
            pass

    # --- Domain Authorization ---

    def get_authorized_domains(self) -> list[str]:
        """Get the list of domains the user has authorized."""
        return list(self._authorized_domains)

    async def set_authorized_domains(self, domains: list[str]) -> None:
        """Update authorized domains and notify extension."""
        self._authorized_domains = domains
        if self._connected and self._ws:
            try:
                await self._ws.send_text(json.dumps({
                    "type": "set_domains",
                    "domains": domains,
                }))
            except Exception as exc:
                logger.warning("Failed to notify extension of domain change: %s", exc)


_bridge_instance: ExtensionBridgeService | None = None


def get_extension_bridge() -> ExtensionBridgeService:
    """Get or create the singleton ExtensionBridgeService."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ExtensionBridgeService()
    return _bridge_instance
