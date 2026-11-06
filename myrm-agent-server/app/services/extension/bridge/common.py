"""[INPUT]
- app.services.extension.cdp_relay.manager::get_cdp_relay_manager (POS: relay manager)

[OUTPUT]
- logger/constants, DomainPolicyWarning, _broadcast_extension_status, get_cdp_relay_manager

[POS]
Shared primitives of the extension bridge: the only place tests patch the status broadcast and the relay manager.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.event import AppEvent, AppEventType, get_event_bus
from app.services.extension.cdp_relay.manager import get_cdp_relay_manager as get_cdp_relay_manager

if TYPE_CHECKING:
    pass


try:
    from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
        ExtensionBridgeNotAvailable,
        ExtensionStatus,
        ExtensionTab,
    )
except ImportError:
    from dataclasses import dataclass

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
