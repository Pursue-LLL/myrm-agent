"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- RelayMixin

[POS]
Extension bridge mixin: websocket relay: handshake, receive/heartbeat loops, requests and tab sync.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

from starlette.websockets import WebSocket, WebSocketDisconnect

from app.services.extension.access_policy import (
    is_blank_url,
    normalize_domain_patterns,
    prune_paused_tab_ids,
)
from app.services.extension.cdp_relay.protocol import RelayTabInfo

if TYPE_CHECKING:
    from patchright.async_api import Browser

from . import common
from .common import (
    _HEARTBEAT_INTERVAL,
    _HEARTBEAT_TIMEOUT,
    ExtensionBridgeNotAvailable,
    logger,
)


class RelayMixin:
    async def handle_ws_connection(self, ws: WebSocket) -> None:
        """Handle incoming WebSocket connection from the browser extension."""
        await ws.accept()

        async with self._lock:
            if self._ws is not None:
                await self.disconnect()
            self._ws = ws
            self._connected = True
            self._hello_received = False
            self._capabilities.clear()
            self._last_heartbeat = time.monotonic()

        logger.info("Extension bridge connected")
        common._broadcast_extension_status(True)

        self._receive_task = asyncio.create_task(self._receive_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            await self._receive_task
        except asyncio.CancelledError:
            pass
        finally:
            await self._release_connection(ws)

    async def _release_connection(self, ws: WebSocket) -> None:
        """Forget a closed extension connection and everything that only lived on it, unless a newer one replaced it."""
        if self._ws is not None and self._ws is not ws:
            return
        self._connected = False
        self._ws = None
        self._hello_received = False
        self._capabilities.clear()
        self._tabs = []
        self._agent_tabs = {}
        for fut in self._pending_requests.values():
            if not fut.done():
                fut.set_exception(ExtensionBridgeNotAvailable("Connection lost"))
        self._pending_requests.clear()
        # The debugger sessions died with the connection; the relay must tell its CDP clients instead of leaving them stranded.
        await common.get_cdp_relay_manager().bind_extension_transport(None)
        logger.info("Extension bridge WebSocket closed")
        common._broadcast_extension_status(False)

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
                    self._capabilities = self._normalize_capabilities(msg.get("capabilities"))
                    self._hello_received = True
                    relay = common.get_cdp_relay_manager()
                    relay.set_identity(
                        user_agent=str(msg.get("userAgent") or ""),
                        browser_version=str(msg.get("browserVersion") or self._browser_name),
                    )
                    await relay.bind_extension_transport(self._send_ws_message)
                    await self._notify_extension_access_policy()
                    await self._sync_relay_tabs()
                    logger.info(
                        "Extension hello: %s on %s (capabilities=%s)",
                        self._extension_version,
                        self._browser_name,
                        sorted(self._capabilities),
                    )

                elif msg_type in ("relay_result", "relay_error", "cdp_event", "debugger_detached"):
                    await common.get_cdp_relay_manager().dispatch_extension_message(msg)

                elif msg_type == "tabs_update":
                    self._apply_tab_list(msg.get("tabs"))
                    active_tab_ids = frozenset(tab.tab_id for tab in self._tabs)
                    pruned_paused = prune_paused_tab_ids(
                        self._paused_tab_ids,
                        active_tab_ids,
                    )
                    if pruned_paused != self._paused_tab_ids:
                        self._paused_tab_ids = pruned_paused
                        await self._notify_extension_access_policy()
                    await self._sync_relay_tabs()

                elif msg_type == "response":
                    req_id = msg.get("id", "")
                    if req_id in self._pending_requests:
                        fut = self._pending_requests.pop(req_id)
                        if msg.get("error"):
                            fut.set_exception(ExtensionBridgeNotAvailable(msg["error"]))
                        else:
                            fut.set_result(msg.get("data"))

                elif msg_type == "domains_update":
                    raw_domains = msg.get("domains", [])
                    if isinstance(raw_domains, list):
                        self._authorized_domains = normalize_domain_patterns([str(item) for item in raw_domains])
                    await self._sync_relay_tabs()

                elif msg_type == "access_policy_update":
                    self._apply_access_policy_payload(msg)
                    await self._sync_relay_tabs()

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

    async def _send_ws_message(self, msg: dict[str, object]) -> None:
        if not self._connected or self._ws is None:
            raise ExtensionBridgeNotAvailable("Extension not connected")
        await self._ws.send_text(json.dumps(msg))

    async def _sync_relay_tabs(self) -> None:
        relay = common.get_cdp_relay_manager()
        relay.sync_tabs_from_extension(
            [
                RelayTabInfo(
                    tab_id=tab.tab_id,
                    url=tab.url,
                    title=tab.title,
                    active=tab.active,
                    # Handed to the Agent once it holds a document: a page still blank when the client starts setting it up
                    # can leave the authorized sites before the client is done.
                    opener_tab_id=None if is_blank_url(tab.url) else self._agent_tabs.get(tab.tab_id),
                )
                for tab in self._tabs
                if self._tab_is_accessible(tab) or self._is_blank_agent_tab(tab)
            ]
        )

    async def _focus_browser_on_domain(self, browser: Browser, domain: str) -> None:
        from urllib.parse import urlparse

        domain_lower = domain.strip().lower().rstrip(".")
        for context in browser.contexts:
            for page in context.pages:
                try:
                    page_url = page.url or ""
                except Exception:
                    continue
                host = (urlparse(page_url).hostname or "").strip().lower().rstrip(".")
                if host and self._match_domain(host, [domain_lower]):
                    try:
                        await page.bring_to_front()
                    except Exception as exc:
                        logger.debug("Failed to focus page for domain %s: %s", domain, exc)
                    return

    async def _send_request(
        self,
        action: str,
        payload: dict[str, object] | None = None,
        *,
        timeout: float = 10.0,
    ) -> object:
        """Send a request to the extension and wait for response."""
        if not self._connected or not self._ws:
            raise ExtensionBridgeNotAvailable("Extension not connected")
        self._require_action_capability(action)

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
        except asyncio.TimeoutError as exc:
            self._pending_requests.pop(req_id, None)
            raise ExtensionBridgeNotAvailable(f"Extension request '{action}' timed out") from exc

    async def _request_debugger_attach(
        self,
        domain: str | None = None,
        tab_id: int | None = None,
        *,
        background: bool = False,
        timeout: float = 10.0,
    ) -> int:
        """Request the extension to attach chrome.debugger to a tab.

        Returns the tab ID that was attached. The extension uses its privileged
        chrome.debugger API to control the tab — no external CDP endpoint needed.

        When *tab_id* is provided the extension attaches directly to that tab.
        When *background* is False (default for login-state tabs), the extension
        prefers the user's existing foreground tab for the domain.
        """
        payload: dict[str, object] = {}
        if tab_id is not None:
            payload["tabId"] = tab_id
        elif domain:
            payload["domain"] = domain

        payload["background"] = background

        result = await self._send_request("attach_debugger", payload, timeout=timeout)
        if not isinstance(result, dict):
            raise ExtensionBridgeNotAvailable("Extension returned invalid attach_debugger response")

        attached_tab_id = result.get("tabId") or result.get("tab_id")
        if not attached_tab_id:
            raise ExtensionBridgeNotAvailable("Extension did not return attached tab ID")
        return int(attached_tab_id)

    async def _refresh_tabs(self) -> None:
        """Request fresh tab list from extension."""
        try:
            self._apply_tab_list(await self._send_request("list_tabs", timeout=5.0))
        except ExtensionBridgeNotAvailable:
            pass
