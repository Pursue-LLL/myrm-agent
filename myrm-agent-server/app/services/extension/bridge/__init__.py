"""Browser extension bridge.

[INPUT]
- .service / .factory (POS: bridge service and singleton)

[OUTPUT]
- ExtensionBridgeService, get_extension_bridge, DomainPolicyWarning

[POS]
Aggregate exit of the extension bridge package.
"""

from __future__ import annotations

from .common import (
    DomainPolicyWarning,
    ExtensionBridgeNotAvailable,
    ExtensionStatus,
    ExtensionTab,
    _broadcast_extension_status,
    get_cdp_relay_manager,
)
from .factory import _bridge_instance, get_extension_bridge
from .service import ExtensionBridgeService

__all__ = [
    "ExtensionTab",
    "ExtensionStatus",
    "ExtensionBridgeNotAvailable",
    "ExtensionBridgeService",
    "DomainPolicyWarning",
    "_broadcast_extension_status",
    "_bridge_instance",
    "get_cdp_relay_manager",
    "get_extension_bridge",
]
