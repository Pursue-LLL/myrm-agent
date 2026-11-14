"""[INPUT]
- .connection / .access / .relay / .tabs / .capability / .clip_config (POS: the six mixins)

[OUTPUT]
- ExtensionBridgeService

[POS]
The extension bridge: behaviour composed from the six mixins over their shared BridgeState.
"""

from __future__ import annotations

from .access import AccessPolicyMixin
from .capability import CapabilityMixin
from .clip_config import ClipConfigMixin
from .connection import ConnectionMixin
from .relay import RelayMixin
from .tabs import TabsMixin


class ExtensionBridgeService(ConnectionMixin, AccessPolicyMixin, RelayMixin, TabsMixin, CapabilityMixin, ClipConfigMixin):
    """Manages the WebSocket connection to the browser extension.

    Singleton per server instance (one user = one extension connection in sandbox model).
    Implements the ExtensionBridge Protocol for harness integration.
    """
