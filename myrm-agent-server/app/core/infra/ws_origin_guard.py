"""WebSocket Origin validation guard.

Prevents Cross-Site WebSocket Hijacking (CSWSH) by verifying the Origin header
against the configured CORS origins allowlist before accepting connections.

Strategy:
  - No Origin header → allow (non-browser client, not vulnerable to CSWSH)
  - Origin present and in cors_origins → allow
  - Origin present but not in cors_origins → reject with close code 4003

This reuses the same cors_origins configuration as HTTP CORS middleware,
ensuring a unified security boundary for both HTTP and WebSocket traffic.

[INPUT]
- app.config.settings::settings (POS: Application settings singleton)
- app.core.infra.cors_validator::parse_and_validate_cors_origins (POS: CORS origins parser)
- app.core.infra.cors_validator::CORS_ORIGINS_DEFAULT (POS: CORS origins parser)

[OUTPUT]
- verify_ws_origin: Async guard function for WS endpoints (call before ws.accept())

[POS]
WebSocket Origin guard. Validates browser Origin header against cors_origins before accepting WS connections.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import WebSocket

from app.config.settings import settings
from app.core.infra.cors_validator import CORS_ORIGINS_DEFAULT, parse_and_validate_cors_origins

logger = logging.getLogger(__name__)

_WS_CLOSE_ORIGIN_REJECTED = 4003


@lru_cache(maxsize=1)
def _get_allowed_origins() -> frozenset[str]:
    """Parse and cache the allowed origins set (called once at first WS connection)."""
    origins = parse_and_validate_cors_origins(settings.cors_origins or CORS_ORIGINS_DEFAULT)
    return frozenset(origins)


async def verify_ws_origin(ws: WebSocket) -> bool:
    """Verify the WebSocket connection's Origin header against allowed origins.

    Must be called BEFORE ws.accept(). Returns True if the connection should
    proceed, False if it was rejected and closed.

    Args:
        ws: The incoming WebSocket connection (not yet accepted).

    Returns:
        True if origin is valid or absent (non-browser), False if rejected.
    """
    origin = ws.headers.get("origin")

    if not origin:
        return True

    allowed = _get_allowed_origins()
    if origin in allowed:
        return True

    logger.warning(
        "WebSocket connection rejected: origin '%s' not in allowed origins",
        origin,
    )
    await ws.close(code=_WS_CLOSE_ORIGIN_REJECTED, reason="Origin not allowed")
    return False
