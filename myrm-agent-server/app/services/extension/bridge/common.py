"""[INPUT]
- app.services.extension.cdp_relay.manager::get_cdp_relay_manager (POS: relay manager)
- myrm_agent_harness.toolkits.browser.pool.extension_bridge::ExtensionBridgeNotAvailable, ExtensionStatus, ExtensionTab (POS: the contract types the bridge exchanges with the harness)

[OUTPUT]
- logger/constants, DomainPolicyWarning, _broadcast_extension_status, get_cdp_relay_manager
- ExtensionBridgeNotAvailable, ExtensionStatus, ExtensionTab (re-exported contract types)

[POS]
Shared primitives of the extension bridge: the only place tests patch the status broadcast and the relay manager.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from myrm_agent_harness.toolkits.browser.pool.extension_bridge import (
    ExtensionBridgeNotAvailable as ExtensionBridgeNotAvailable,
)
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionStatus as ExtensionStatus
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionTab as ExtensionTab

from app.services.event import AppEvent, AppEventType, get_event_bus
from app.services.extension.cdp_relay.manager import get_cdp_relay_manager as get_cdp_relay_manager

logger = logging.getLogger(__name__)


_HEARTBEAT_INTERVAL = 15.0


_HEARTBEAT_TIMEOUT = 30.0


# The CDP relay needs an extension that reports the browser's own target ids, opens and closes only its own tabs and
# admits the blank pages it opened; an older extension would hang Playwright instead of failing.
RELAY_CAPABILITY = "agent_tab_control"


_ACTION_CAPABILITY_MAP: dict[str, str] = {
    "navigate_url": "navigate_url",
    "list_tabs": "list_tabs",
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
