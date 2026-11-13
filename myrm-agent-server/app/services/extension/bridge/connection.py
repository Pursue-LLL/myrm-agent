"""[INPUT]
- .common (POS: shared primitives)
- myrm_agent_harness.api::is_driver_closed_error (POS: tells a connect that failed on an exited Playwright driver from other failures)

[OUTPUT]
- ConnectionMixin

[POS]
Extension bridge mixin: connect/disconnect, CDP endpoint resolution, navigation and status. A connect that finds the
Playwright driver process exited drops that driver and attaches again on a new one, so a dead driver never fails a
connect (it would otherwise fail every one until the extension reconnects). Callers that need a driver while one is
starting share it.
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

from myrm_agent_harness.api import is_driver_closed_error
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionBrowserInstance
from starlette.websockets import WebSocketState

from app.services.extension.access_policy import (
    is_navigation_target_allowed,
)

if TYPE_CHECKING:
    from patchright.async_api import Browser, Playwright

from . import common
from .common import (
    RELAY_CAPABILITY,
    ExtensionBridgeNotAvailable,
    ExtensionStatus,
    ExtensionTab,
    logger,
)
from .state import BridgeState


class ConnectionMixin(BridgeState):
    async def _ensure_playwright(self) -> Playwright:
        """Return the cached Playwright instance, starting one if needed.

        Callers that arrive while a driver is starting wait and share it: each starting its own would overwrite the
        cache and leave every driver but the last running with nothing to stop it.
        """
        async with self._playwright_lock:
            if self._playwright is None:
                from patchright.async_api import async_playwright

                self._playwright = await async_playwright().start()
            return self._playwright

    async def _discard_playwright(self) -> None:
        """Stop and forget the cached driver, so the next ``_ensure_playwright`` starts a new one.

        The cache is cleared first: a caller that arrives while the old driver is still stopping must not pick it up.
        """
        playwright, self._playwright = self._playwright, None
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()

    async def _attach_once(self, cdp_endpoint: str, timeout: float) -> Browser:
        """One Playwright attach to the relay's DevTools endpoint, on the cached driver.

        A driver whose process has exited can attach to nothing, ever, so it is dropped before the error propagates.
        Only the driver that failed is dropped: a newer one another caller already started keeps serving.
        """
        pw = await self._ensure_playwright()
        try:
            return await pw.chromium.connect_over_cdp(cdp_endpoint, timeout=timeout * 1000)
        except Exception as exc:
            if self._playwright is pw and is_driver_closed_error(exc):
                await self._discard_playwright()
            raise

    async def _connect_over_cdp(self, cdp_endpoint: str, timeout: float) -> Browser:
        """Attach Playwright to the relay's DevTools endpoint, once more on a new driver if the cached one had exited.

        The retry belongs here: the bridge owns the driver, and the browser pool's own single retry of a failed page
        acquisition would otherwise be spent reaching this same dead driver, leaving the session without a tab.
        """
        try:
            return await self._attach_once(cdp_endpoint, timeout)
        except Exception as exc:
            if not is_driver_closed_error(exc):
                raise
            logger.warning("Extension bridge: Playwright driver process is gone (%s); attaching again on a new driver", exc)
            return await self._attach_once(cdp_endpoint, timeout)

    def _resolve_cdp_endpoint(self) -> str | None:
        """Discover main Chrome CDP endpoint when extension bridge has no cached value."""
        if self._cdp_endpoint:
            return self._cdp_endpoint
        from myrm_agent_harness.toolkits.browser.pool.chrome_discovery import (
            discover_chrome_cdp_endpoint,
        )

        discovered = discover_chrome_cdp_endpoint()
        if discovered:
            self._cdp_endpoint = discovered
            logger.info("Extension bridge: discovered main Chrome CDP at %s", discovered)
        return self._cdp_endpoint

    def has_direct_cdp_endpoint(self, *, probe_ttl_s: float = 15.0) -> bool:
        """Best-effort check for a local direct CDP endpoint with negative caching.

        UI polls setup-hints frequently. Without a short TTL for negative probes, each poll
        would trigger filesystem/network discovery work. This method keeps endpoint checks
        responsive while avoiding excessive discovery churn when CDP is not configured.
        """
        if self._cdp_endpoint:
            return True

        now = time.monotonic()
        if now - self._last_cdp_probe_monotonic < probe_ttl_s:
            return False

        self._last_cdp_probe_monotonic = now
        return self._resolve_cdp_endpoint() is not None

    async def _resolve_playwright_cdp_endpoint(self) -> str:
        self._require_capability(RELAY_CAPABILITY)
        relay = common.get_cdp_relay_manager()
        await relay.bind_extension_transport(self._send_ws_message)
        if await relay.relay_cdp_ready():
            return await relay.ensure_http_endpoint()

        raise ExtensionBridgeNotAvailable("Extension CDP relay is not ready. Reconnect the browser extension and retry.")

    async def connect(self, *, timeout: float = 10.0) -> ExtensionBrowserInstance:
        if not self._connected or self._ws is None:
            raise ExtensionBridgeNotAvailable("Browser extension is not connected. Please install and connect the extension.")
        if not self._hello_received:
            raise ExtensionBridgeNotAvailable("Extension handshake is not completed yet. Reconnect extension and retry.")
        if not self.is_access_policy_valid():
            raise ExtensionBridgeNotAvailable(
                "Extension access policy is not configured. "
                "Add authorized domains or enable allow-all in Settings → Browser Extension."
            )

        await self._sync_relay_tabs()
        cdp_endpoint = await self._resolve_playwright_cdp_endpoint()

        browser = await self._connect_over_cdp(cdp_endpoint, timeout)
        return ExtensionBrowserInstance(browser=browser)

    async def navigate_to_url(
        self,
        url: str,
        *,
        domain: str | None = None,
        background: bool = True,
        timeout: float = 20.0,
    ) -> ExtensionTab:
        """Navigate a tab through extension APIs without direct local CDP dependency."""
        from urllib.parse import urlparse

        target_domain = (urlparse(url).hostname or "").strip().lower().rstrip(".")
        if not target_domain:
            raise ExtensionBridgeNotAvailable(f"Cannot navigate '{url}': unable to resolve target domain")

        requested_domain = (domain or "").strip().lower().rstrip(".")
        if requested_domain and requested_domain != target_domain and not self._match_domain(target_domain, [requested_domain]):
            raise ExtensionBridgeNotAvailable(f"Domain '{requested_domain}' does not match navigation target '{target_domain}'.")

        if not is_navigation_target_allowed(url, self._current_access_policy()):
            policy = self._current_access_policy()
            raise ExtensionBridgeNotAvailable(
                f"Domain '{target_domain}' is not authorized. Authorized domains: {policy.authorized_domains}"
            )
        if not self._connected or self._ws is None:
            raise ExtensionBridgeNotAvailable("Browser extension is not connected.")

        result = await self._send_request(
            "navigate_url",
            {"url": url, "domain": target_domain, "background": background},
            timeout=timeout,
        )
        if not isinstance(result, dict):
            raise ExtensionBridgeNotAvailable("Extension returned invalid navigate_url response")

        tab_id_raw = result.get("tabId") or result.get("id")
        if tab_id_raw is None:
            raise ExtensionBridgeNotAvailable("Extension navigate_url did not return tab ID")

        return ExtensionTab(
            tab_id=int(tab_id_raw),
            url=str(result.get("url") or url),
            title=str(result.get("title") or ""),
            domain=str(result.get("domain") or target_domain),
            active=bool(result.get("active", False)),
        )

    async def get_status(self) -> ExtensionStatus:
        accessible_tabs = [tab for tab in self._tabs if self._tab_is_visible_in_ui(tab)]
        return ExtensionStatus(
            connected=self._connected,
            handshake_ready=self._hello_received,
            extension_version=self._extension_version,
            browser_name=self._browser_name,
            authorized_domains=list(self._authorized_domains),
            available_tabs=accessible_tabs,
            last_heartbeat_at=self._last_heartbeat,
            capabilities=sorted(self._capabilities),
        )

    def is_connected(self) -> bool:
        return self._connected

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
        await common.get_cdp_relay_manager().bind_extension_transport(None)
        await self._discard_playwright()
        self._connected = False
        self._ws = None
        self._hello_received = False
        self._capabilities.clear()
        self._tabs = []
        logger.info("Extension bridge disconnected")
        common._broadcast_extension_status(False)

    async def relay_cdp_ready(self) -> bool:
        """True when extension CDP relay responds to automation probe."""
        if not self.is_access_policy_valid() or RELAY_CAPABILITY not in self._capabilities:
            return False
        relay = common.get_cdp_relay_manager()
        if self._connected and self._ws is not None:
            await relay.bind_extension_transport(self._send_ws_message)
            await self._sync_relay_tabs()
        return await relay.relay_cdp_ready()
