"""Lifecycle manager for extension CDP relay (singleton per server process).

[INPUT]
- cdp_relay.bridge::ExtensionCdpRelayBridge (POS: CDP relay bridge)
- cdp_relay.server::LoopbackCdpRelayServer (POS: loopback DevTools HTTP/WS server)

[OUTPUT]
- CdpRelayManager: relay lifecycle + relay_cdp_ready probe cache
- get_cdp_relay_manager: process singleton accessor

[POS]
Owns CDP relay bridge and loopback server lifecycle; wired to ExtensionBridgeService WS.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from .bridge import ExtensionCdpRelayBridge, build_extension_call_extension
from .protocol import RelayTabInfo
from .server import LoopbackCdpRelayServer

logger = logging.getLogger(__name__)

SendToExtension = Callable[[dict[str, object]], Awaitable[None]]

_PROBE_CACHE_TTL_S = 3.0


class CdpRelayManager:
    """Owns relay bridge + loopback server; wired to ExtensionBridgeService WS."""

    def __init__(self) -> None:
        self._bridge = ExtensionCdpRelayBridge()
        self._server = LoopbackCdpRelayServer(self._bridge)
        self._http_endpoint: str | None = None
        self._send_to_extension: SendToExtension | None = None
        self._probe_cached_at: float = 0.0
        self._probe_cached_value: bool = False

    @property
    def bridge(self) -> ExtensionCdpRelayBridge:
        return self._bridge

    @property
    def http_endpoint(self) -> str | None:
        return self._http_endpoint

    async def bind_extension_transport(self, send_to_extension: SendToExtension | None) -> None:
        self._send_to_extension = send_to_extension
        if send_to_extension is None:
            self._bridge.set_extension_transport(None)
            self._invalidate_probe_cache()
            return
        call_extension = build_extension_call_extension(self._bridge, send_to_extension)
        self._bridge.set_extension_transport(call_extension)
        self._invalidate_probe_cache()
        if self._http_endpoint is None:
            self._http_endpoint = await self._server.start()

    async def shutdown(self) -> None:
        self._bridge.set_extension_transport(None)
        self._send_to_extension = None
        self._invalidate_probe_cache()
        await self._server.stop()
        self._http_endpoint = None

    def _invalidate_probe_cache(self) -> None:
        self._probe_cached_at = 0.0
        self._probe_cached_value = False

    async def relay_cdp_ready(self) -> bool:
        if self._http_endpoint is None:
            return False
        now = time.monotonic()
        if now - self._probe_cached_at < _PROBE_CACHE_TTL_S:
            return self._probe_cached_value
        result = await self._bridge.probe_automation_ready()
        self._probe_cached_at = now
        self._probe_cached_value = result
        return result

    async def ensure_http_endpoint(self) -> str:
        if self._http_endpoint is None:
            self._http_endpoint = await self._server.start()
        if self._http_endpoint is None:
            raise RuntimeError("CDP relay server failed to start")
        return self._http_endpoint

    def set_identity(self, *, user_agent: str = "", browser_version: str = "") -> None:
        self._bridge.set_identity(user_agent=user_agent, browser_version=browser_version)

    def sync_tabs_from_extension(self, tabs: list[RelayTabInfo]) -> None:
        self._bridge.sync_tabs(tabs)

    async def dispatch_extension_message(self, msg: dict[str, object]) -> None:
        msg_type = msg.get("type")
        if msg_type == "relay_result":
            seq_raw = msg.get("seq")
            if isinstance(seq_raw, int):
                await self._bridge.handle_extension_result(seq_raw, msg.get("result"))
            return
        if msg_type == "relay_error":
            seq_raw = msg.get("seq")
            message = str(msg.get("message") or "extension relay error")
            if isinstance(seq_raw, int):
                await self._bridge.handle_extension_error(seq_raw, message)
            return
        if msg_type == "cdp_event":
            tab_raw = msg.get("tabId")
            method = msg.get("method")
            if isinstance(tab_raw, int) and isinstance(method, str):
                session_id = msg.get("sessionId")
                self._bridge.handle_cdp_event(
                    tab_raw,
                    method,
                    msg.get("params"),
                    session_id if isinstance(session_id, str) else None,
                )
            return
        if msg_type == "debugger_detached":
            tab_raw = msg.get("tabId")
            if isinstance(tab_raw, int):
                self._bridge.handle_extension_detached(tab_raw)


_manager: CdpRelayManager | None = None


def get_cdp_relay_manager() -> CdpRelayManager:
    global _manager
    if _manager is None:
        _manager = CdpRelayManager()
    return _manager
