"""Browser Extension API module.

Provides WebSocket endpoint for extension connection and REST APIs for
domain authorization management.
"""

from app.api.extension.router import router, ws_router

__all__ = ["router", "ws_router"]
