"""Browser Extension Bridge service.

Manages WebSocket connections from the official browser extension (Chrome/Edge MV3),
providing CDP proxy capabilities for Agent browser automation tasks.
"""

from app.services.extension.bridge import ExtensionBridgeService

__all__ = ["ExtensionBridgeService"]
