"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- ConnectionMixin

[POS]
Extension bridge mixin: connect/disconnect, CDP endpoint resolution, navigation and status.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionBrowserInstance
from starlette.websockets import WebSocketState

from app.services.extension.access_policy import (
    is_navigation_target_allowed,
)

if TYPE_CHECKING:
    from patchright.async_api import Playwright

from . import common
from .common import (
    RELAY_CAPABILITY,
    ExtensionBridgeNotAvailable,
    ExtensionStatus,
    ExtensionTab,
    logger,
)


class ConnectionMixin:
    async def _ensure_playwright(self) -> Playwright:
        """Return the cached Playwright instance, starting one if needed."""
        if self._playwright is None:
            from patchright.async_api import async_playwright

            self._playwright = await async_playwright().start()
        return self._playwright

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
        pw = await self._ensure_playwright()

        browser = await pw.chromium.connect_over_cdp(cdp_endpoint, timeout=timeout * 1000)
        return ExtensionBrowserInstance(browser=browser)

    async def connect_to_domain(self, domain: str, *, timeout: float = 10.0) -> ExtensionBrowserInstance:
        policy = self._current_access_policy()
        domain_lower = domain.strip().lower().rstrip(".")
        if not domain_lower:
            raise ExtensionBridgeNotAvailable("Domain must not be empty.")
        if policy.allow_all_eligible_tabs:
            probe_url = f"https://{domain_lower}"
            if not is_navigation_target_allowed(probe_url, policy):
                raise ExtensionBridgeNotAvailable(f"Domain '{domain}' is not an eligible automation target.")
        elif not self._match_domain(domain_lower, policy.authorized_domains):
            raise ExtensionBridgeNotAvailable(
                f"Domain '{domain}' is not authorized. Authorized domains: {policy.authorized_domains}"
            )

        if not self._connected or self._ws is None:
            raise ExtensionBridgeNotAvailable("Browser extension is not connected.")

        if not self._hello_received:
            raise ExtensionBridgeNotAvailable("Extension handshake is not completed yet. Reconnect extension and retry.")

        await self._refresh_tabs()
        domain_lower = domain.strip().lower().rstrip(".")
        matching = [tab for tab in self._tabs if self._match_domain(tab.domain, [domain_lower])]
        if not matching:
            await self.navigate_to_url(
                f"https://{domain_lower}",
                domain=domain_lower,
                background=False,
                timeout=timeout,
            )
            await self._refresh_tabs()
            matching = [tab for tab in self._tabs if self._match_domain(tab.domain, [domain_lower])]

        if not matching:
            raise ExtensionBridgeNotAvailable(f"No extension tab available for domain '{domain_lower}'.")

        active_matches = [tab for tab in matching if tab.active]
        target_tab = active_matches[0] if active_matches else matching[0]

        await self._sync_relay_tabs()
        cdp_endpoint = await self._resolve_playwright_cdp_endpoint()
        pw = await self._ensure_playwright()

        browser = await pw.chromium.connect_over_cdp(cdp_endpoint, timeout=timeout * 1000)
        await self._focus_browser_on_domain(browser, target_tab.domain)
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
        from app.services.extension.tab_borrow_ledger import get_tab_borrow_ledger

        try:
            await get_tab_borrow_ledger().restore_all(self._send_move_tab)
        except Exception as exc:
            logger.debug("Suppressed error restoring borrowed tabs during disconnect: %s", exc)

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
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
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
