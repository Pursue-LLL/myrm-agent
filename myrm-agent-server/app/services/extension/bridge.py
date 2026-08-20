"""Extension Bridge Service — business-layer implementation.

[INPUT]
- fastapi::WebSocket (POS: WebSocket connection from browser extension)
- myrm_agent_harness.toolkits.browser.pool.extension_bridge::ExtensionBridge (POS: Protocol contract)
- myrm_agent_harness.toolkits.browser.pool.extension_bridge::ExtensionTab, ExtensionStatus
- myrm_agent_harness.toolkits.browser.pool.browser_launcher::BrowserInstance
- app.services.extension.access_policy (POS: 统一 tab 访问策略评估)

[OUTPUT]
- ExtensionBridgeService: Singleton managing extension WebSocket connection and tab control

[POS]
Business layer bridge connecting the browser extension (MV3 WebSocket) to the harness
BrowserLauncher. Implements the ExtensionBridge Protocol defined in the harness layer.
Handles: connection lifecycle, heartbeat, domain authorization, tab listing, debugger
attach orchestration, CDP relay orchestration for Playwright connect_over_cdp (fail-closed;
no direct local CDP fallback in extension mode).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.browser.pool.browser_launcher import BrowserInstance
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

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
        handshake_ready: bool = False
        extension_version: str = ""
        browser_name: str = ""
        authorized_domains: list[str] = field(default_factory=list)
        available_tabs: list[ExtensionTab] = field(default_factory=list)
        last_heartbeat_at: float = 0.0
        capabilities: list[str] = field(default_factory=list)


if TYPE_CHECKING:
    from patchright.async_api import Browser, Playwright

from app.services.event import AppEvent, AppEventType, get_event_bus
from app.services.extension.access_policy import (
    ExtensionAccessPolicy,
    is_navigation_target_allowed,
    is_policy_valid_for_automation,
    is_tab_accessible,
    match_domain,
    normalize_domain_patterns,
    prune_paused_tab_ids,
)
from app.services.extension.cdp_relay.manager import get_cdp_relay_manager
from app.services.extension.cdp_relay.protocol import RelayTabInfo

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 15.0
_HEARTBEAT_TIMEOUT = 30.0
_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "navigate_url": "navigate_url",
    "list_tabs": "list_tabs",
    "attach_debugger": "attach_debugger",
    "detach_debugger": "detach_debugger",
}


@dataclass(frozen=True)
class DomainPolicyWarning:
    """Structured warning returned when domain policy has surprising semantics."""

    code: str
    pattern: str
    root_domain: str


def _broadcast_extension_status(connected: bool) -> None:
    """Publish extension connection status change via SSE event bus."""
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.EXTENSION_STATUS_CHANGED,
            data={"connected": connected},
        )
    )


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
        self._hello_received = False
        self._capabilities: set[str] = set()
        self._authorized_domains: list[str] = []
        self._allow_all_eligible_tabs = False
        self._paused_tab_ids: frozenset[int] = frozenset()
        self._tabs: list[ExtensionTab] = []
        self._last_heartbeat: float = 0.0
        self._pending_requests: dict[str, asyncio.Future[object]] = {}
        self._request_counter = 0
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._cdp_endpoint: str | None = None
        self._last_cdp_probe_monotonic = 0.0
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
        """Check if *domain* matches any pattern in *patterns*."""
        return match_domain(domain, patterns)

    def _current_access_policy(self) -> ExtensionAccessPolicy:
        return ExtensionAccessPolicy(
            allow_all_eligible_tabs=self._allow_all_eligible_tabs,
            authorized_domains=list(self._authorized_domains),
            paused_tab_ids=self._paused_tab_ids,
        )

    def _tab_is_accessible(self, tab: ExtensionTab) -> bool:
        return is_tab_accessible(
            tab_id=tab.tab_id,
            url=tab.url,
            domain=tab.domain,
            policy=self._current_access_policy(),
        )

    def _tab_is_visible_in_ui(self, tab: ExtensionTab) -> bool:
        return is_tab_accessible(
            tab_id=tab.tab_id,
            url=tab.url,
            domain=tab.domain,
            policy=self._current_access_policy(),
            respect_pause=False,
        )

    def is_access_policy_valid(self) -> bool:
        return is_policy_valid_for_automation(self._current_access_policy())

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

    @staticmethod
    def _normalize_capabilities(raw: object) -> set[str]:
        """Normalize extension capability payload to a lowercase token set."""
        if not isinstance(raw, list):
            return set()
        normalized: set[str] = set()
        for item in raw:
            if isinstance(item, str):
                cap = item.strip().lower()
                if cap:
                    normalized.add(cap)
        return normalized

    def _require_capability(self, capability: str) -> None:
        """Ensure extension handshake completed and capability is available."""
        if not self._hello_received:
            raise ExtensionBridgeNotAvailable("Extension handshake is not completed yet. Reconnect extension and retry.")
        if capability not in self._capabilities:
            raise ExtensionBridgeNotAvailable(
                f"Extension missing required capability '{capability}'. Please upgrade the browser extension and reconnect."
            )

    def _require_action_capability(self, action: str) -> None:
        """Enforce action-level capability contract for extension requests."""
        capability = _ACTION_CAPABILITY_MAP.get(action)
        if capability:
            self._require_capability(capability)

    @staticmethod
    def analyze_domain_policy_warnings(domains: list[str]) -> list[DomainPolicyWarning]:
        """Return warnings for surprising but valid domain policy inputs."""
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in domains:
            item = raw.strip().lower().rstrip(".")
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)

        normalized_set = set(normalized)
        warnings: list[DomainPolicyWarning] = []
        for pattern in normalized:
            if not pattern.startswith("*."):
                continue
            root = pattern[2:]
            if not root or root in normalized_set:
                continue
            warnings.append(
                DomainPolicyWarning(
                    code="wildcard_includes_root",
                    pattern=pattern,
                    root_domain=root,
                )
            )
        return warnings

    async def relay_cdp_ready(self) -> bool:
        """True when extension CDP relay responds to automation probe."""
        if not self.is_access_policy_valid():
            return False
        relay = get_cdp_relay_manager()
        if self._connected and self._ws is not None:
            await relay.bind_extension_transport(self._send_ws_message)
            await self._sync_relay_tabs()
        return await relay.relay_cdp_ready()

    async def _resolve_playwright_cdp_endpoint(self) -> str:
        relay = get_cdp_relay_manager()
        await relay.bind_extension_transport(self._send_ws_message)
        if await relay.relay_cdp_ready():
            return await relay.ensure_http_endpoint()

        raise ExtensionBridgeNotAvailable("Extension CDP relay is not ready. Reconnect the browser extension and retry.")

    async def connect(self, *, timeout: float = 10.0) -> BrowserInstance:
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
        preferred = self._pick_preferred_extension_tab()
        if preferred is not None:
            await self._focus_browser_on_domain(browser, preferred.domain)
        return BrowserInstance(
            browser=browser,
            engine="chromium-patchright",
            is_managed=False,
            _pid=None,
        )

    async def connect_to_domain(self, domain: str, *, timeout: float = 10.0) -> BrowserInstance:
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
        return BrowserInstance(
            browser=browser,
            engine="chromium-patchright",
            is_managed=False,
            _pid=None,
        )

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

    async def list_tabs(self) -> list[ExtensionTab]:
        if not self._connected:
            return []
        await self._refresh_tabs()
        return [tab for tab in self._tabs if self._tab_is_accessible(tab)]

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
        await get_cdp_relay_manager().bind_extension_transport(None)
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
        _broadcast_extension_status(False)

    # --- WebSocket Session Management ---

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
        _broadcast_extension_status(True)

        self._receive_task = asyncio.create_task(self._receive_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            await self._receive_task
        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            self._ws = None
            self._hello_received = False
            self._capabilities.clear()
            for fut in self._pending_requests.values():
                if not fut.done():
                    fut.set_exception(ExtensionBridgeNotAvailable("Connection lost"))
            self._pending_requests.clear()
            logger.info("Extension bridge WebSocket closed")
            _broadcast_extension_status(False)

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
                    relay = get_cdp_relay_manager()
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
                    await get_cdp_relay_manager().dispatch_extension_message(msg)

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

    # --- Internal Helpers ---

    async def _send_ws_message(self, msg: dict[str, object]) -> None:
        if not self._connected or self._ws is None:
            raise ExtensionBridgeNotAvailable("Extension not connected")
        await self._ws.send_text(json.dumps(msg))

    async def _sync_relay_tabs(self) -> None:
        relay = get_cdp_relay_manager()
        relay.sync_tabs_from_extension(
            [
                RelayTabInfo(
                    tab_id=tab.tab_id,
                    url=tab.url,
                    title=tab.title,
                    active=tab.active,
                )
                for tab in self._tabs
                if self._tab_is_accessible(tab)
            ]
        )

    def _pick_preferred_extension_tab(self) -> ExtensionTab | None:
        authorized = [tab for tab in self._tabs if self._tab_is_accessible(tab)]
        if not authorized:
            return None
        active = [tab for tab in authorized if tab.active]
        return active[0] if active else authorized[0]

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

    # --- Access policy ---

    def get_access_policy(self) -> ExtensionAccessPolicy:
        return self._current_access_policy()

    def _apply_access_policy_payload(self, msg: dict[str, object]) -> None:
        if "allow_all_eligible_tabs" in msg:
            self._allow_all_eligible_tabs = msg.get("allow_all_eligible_tabs") is True
        if "domains" in msg:
            raw_domains = msg.get("domains")
            if isinstance(raw_domains, list):
                self._authorized_domains = normalize_domain_patterns([str(item) for item in raw_domains])
        if "paused_tab_ids" in msg:
            raw_paused = msg.get("paused_tab_ids")
            if isinstance(raw_paused, list):
                paused: set[int] = set()
                for item in raw_paused:
                    if isinstance(item, int):
                        paused.add(item)
                    elif isinstance(item, str) and item.isdigit():
                        paused.add(int(item))
                self._paused_tab_ids = frozenset(paused)

    async def set_access_policy(
        self,
        *,
        allow_all_eligible_tabs: bool | None = None,
        authorized_domains: list[str] | None = None,
        paused_tab_ids: list[int] | None = None,
    ) -> ExtensionAccessPolicy:
        if allow_all_eligible_tabs is not None:
            self._allow_all_eligible_tabs = allow_all_eligible_tabs
        if authorized_domains is not None:
            self._authorized_domains = normalize_domain_patterns(authorized_domains)
        if paused_tab_ids is not None:
            self._paused_tab_ids = frozenset(paused_tab_ids)
        await self._notify_extension_access_policy()
        if self._connected:
            await self._sync_relay_tabs()
        return self._current_access_policy()

    async def _notify_extension_access_policy(self) -> None:
        if not self._connected or self._ws is None:
            return
        policy = self._current_access_policy()
        try:
            await self._ws.send_text(
                json.dumps(
                    {
                        "type": "set_access_policy",
                        "allow_all_eligible_tabs": policy.allow_all_eligible_tabs,
                        "domains": list(policy.authorized_domains),
                        "paused_tab_ids": sorted(policy.paused_tab_ids),
                    }
                )
            )
        except Exception as exc:
            logger.warning("Failed to notify extension of access policy: %s", exc)

    def get_authorized_domains(self) -> list[str]:
        """Get the list of domains the user has authorized."""
        return list(self._authorized_domains)

    async def set_authorized_domains(self, domains: list[str]) -> None:
        """Update authorized domains and notify extension."""
        await self.set_access_policy(authorized_domains=domains)

    async def notify_clip_agent_config(
        self,
        agent_id: str | None,
        web_ui_origin: str | None,
    ) -> None:
        """Push wiki clip agent scope to the connected extension."""
        if not self._connected or not self._ws:
            return
        try:
            await self._ws.send_text(
                json.dumps(
                    {
                        "type": "clip_agent_update",
                        "agent_id": agent_id,
                        "web_ui_origin": web_ui_origin,
                    }
                )
            )
        except Exception as exc:
            logger.warning("Failed to notify extension of clip agent change: %s", exc)


_bridge_instance: ExtensionBridgeService | None = None


def get_extension_bridge() -> ExtensionBridgeService:
    """Get or create the singleton ExtensionBridgeService."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ExtensionBridgeService()
    return _bridge_instance
