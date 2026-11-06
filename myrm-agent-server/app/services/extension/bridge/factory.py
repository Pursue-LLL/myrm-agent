"""[INPUT]
- .service::ExtensionBridgeService (POS: the bridge service)

[OUTPUT]
- get_extension_bridge / _bridge_instance

[POS]
Process-wide singleton accessor for the extension bridge.
"""

from __future__ import annotations

from .service import ExtensionBridgeService

_bridge_instance: ExtensionBridgeService | None = None


def get_extension_bridge() -> ExtensionBridgeService:
    """Get or create the singleton ExtensionBridgeService."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ExtensionBridgeService()
    return _bridge_instance
