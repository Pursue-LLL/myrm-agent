"""[INPUT]
- .connection / .access / .relay / .tabs / .capability / .clip_config (POS: the six mixins)

[OUTPUT]
- ExtensionBridgeService

[POS]
The extension bridge: session state in __init__, behaviour composed from the six mixins.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from starlette.websockets import WebSocket

if TYPE_CHECKING:
    from patchright.async_api import Playwright

from .access import AccessPolicyMixin
from .capability import CapabilityMixin
from .clip_config import ClipConfigMixin
from .common import ExtensionTab
from .connection import ConnectionMixin
from .relay import RelayMixin
from .tabs import TabsMixin


class ExtensionBridgeService(ConnectionMixin, AccessPolicyMixin, RelayMixin, TabsMixin, CapabilityMixin, ClipConfigMixin):
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
        # Tabs the Agent owns, each with the Agent tab that opened it (None when the Agent opened it itself).
        self._agent_tabs: dict[int, int | None] = {}
        self._last_heartbeat: float = 0.0
        self._pending_requests: dict[str, asyncio.Future[object]] = {}
        self._request_counter = 0
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._cdp_endpoint: str | None = None
        self._last_cdp_probe_monotonic = 0.0
        self._lock = asyncio.Lock()
        self._playwright: Playwright | None = None
