"""[INPUT]
- app.services.extension.access_policy::ExtensionAccessPolicy (POS: the policy value the mixins pass to each other)
- .common (POS: the tab type the mirror holds)

[OUTPUT]
- BridgeState

[POS]
The session state of the extension bridge and the signatures of the methods its mixins call on each other: the one base
every mixin is checked against, so each is type-checked as the service it is composed into.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from starlette.websockets import WebSocket

from app.services.extension.access_policy import ExtensionAccessPolicy

from .common import ExtensionTab

if TYPE_CHECKING:
    from patchright.async_api import Playwright


class BridgeState:
    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._connected = False
        self._extension_version = ""
        self._browser_name = ""
        self._hello_received = False
        self._capabilities: set[str] = set()
        # True once the user set the policy through this server's API. Until then the server holds nothing of its own and
        # takes the policy the extension saved; afterwards the server's policy is the one the extension must hold.
        self._owns_access_policy = False
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

    if TYPE_CHECKING:
        # What the mixins implement for each other. Only the type checker sees these: at runtime the mixins come first in
        # the service's MRO, so a missing implementation raises AttributeError at the call instead of resolving here.

        @staticmethod
        def _match_domain(domain: str, patterns: list[str]) -> bool: ...
        def _current_access_policy(self) -> ExtensionAccessPolicy: ...
        def _tab_is_accessible(self, tab: ExtensionTab) -> bool: ...
        def _tab_is_visible_in_ui(self, tab: ExtensionTab) -> bool: ...
        def _is_blank_agent_tab(self, tab: ExtensionTab) -> bool: ...
        def is_access_policy_valid(self) -> bool: ...
        def _apply_access_policy_report(self, msg: dict[str, object]) -> None: ...
        async def _push_access_policy_if_owned(self) -> None: ...
        async def _notify_extension_access_policy(self) -> None: ...
        def _apply_tab_list(self, raw_tabs: object) -> None: ...
        async def _refresh_tabs(self) -> None: ...
        async def _sync_relay_tabs(self) -> None: ...
        async def _send_ws_message(self, msg: dict[str, object]) -> None: ...
        async def _send_request(
            self,
            action: str,
            payload: dict[str, object] | None = None,
            *,
            timeout: float = 10.0,
        ) -> object: ...
        @staticmethod
        def _normalize_capabilities(raw: object) -> set[str]: ...
        def _require_capability(self, capability: str) -> None: ...
        def _require_action_capability(self, action: str) -> None: ...
        async def disconnect(self) -> None: ...
