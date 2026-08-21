"""Control Plane & internal endpoints authentication and origin security guard.

[INPUT]
- app.config.settings::settings (POS: control_plane.telemetry_token, cors_origins)
- app.core.infra.cors_validator (POS: allowed origins verification)

[OUTPUT]
- verify_control_plane_token: FastAPI dependency verifying CP telemetry token / internal secret
- verify_internal_origin: Helper verifying request Origin / Host header for internal endpoints

[POS]
SSOT security guard for CP-to-Sandbox and internal management endpoints.
Prevents unauthorized local/remote invocations and browser CSRF/DNS-rebinding attacks.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Mapping
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

from app.config.settings import settings
from app.core.infra.cors_validator import CORS_ORIGINS_DEFAULT, parse_and_validate_cors_origins

logger = logging.getLogger(__name__)

CP_TOKEN_HEADER_TELEMETRY = "X-Telemetry-Token"
CP_TOKEN_HEADER_DIRECT = "X-Control-Plane-Token"


def _header_value(headers: Mapping[str, str], name: str) -> str:
    lower_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value.strip()
    return ""


def get_expected_control_plane_token() -> str:
    """Retrieve the expected CP token from settings."""
    token = settings.control_plane.telemetry_token.get_secret_value().strip()
    if token:
        return token
    return settings.internal_service_key.get_secret_value().strip()


def extract_provided_cp_token(request: Request) -> str:
    """Extract provided token from headers (X-Telemetry-Token, X-Control-Plane-Token, or Bearer)."""
    headers = request.headers
    token = _header_value(headers, CP_TOKEN_HEADER_DIRECT)
    if token:
        return token
    token = _header_value(headers, CP_TOKEN_HEADER_TELEMETRY)
    if token:
        return token
    auth_header = _header_value(headers, "Authorization")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return ""


def verify_internal_origin(request: Request) -> None:
    """Verify Origin and Host headers for internal endpoints to prevent browser CSRF/DNS rebinding."""
    origin = request.headers.get("origin")
    if not origin:
        # Non-browser clients (e.g. CP dispatcher httpx, local scripts) omit Origin header
        return

    allowed_origins = set(parse_and_validate_cors_origins(settings.cors_origins or CORS_ORIGINS_DEFAULT))
    normalized_origin = origin.rstrip("/")
    if normalized_origin not in allowed_origins and "*" not in allowed_origins:
        logger.warning("Internal endpoint request rejected: unauthorized origin '%s'", origin)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed for internal endpoint",
        )


async def verify_control_plane_token(request: Request) -> None:
    """FastAPI dependency to verify that a request is authenticated by Control Plane."""
    verify_internal_origin(request)

    expected = get_expected_control_plane_token()
    provided = extract_provided_cp_token(request)

    if not expected:
        # If no CP token configured (e.g. standalone local desktop dev without CP),
        # only allow local loopback clients with valid internal origin.
        from app.core.security.auth.identity import is_loopback_ip

        client_ip = request.client.host if request.client else ""
        if is_loopback_ip(client_ip):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Control plane token not configured and client is not local loopback",
        )

    if not provided or not secrets.compare_digest(provided, expected):
        logger.warning("Invalid or missing Control Plane token for internal endpoint %s", request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Control Plane token",
        )


__all__ = [
    "CP_TOKEN_HEADER_DIRECT",
    "CP_TOKEN_HEADER_TELEMETRY",
    "extract_provided_cp_token",
    "get_expected_control_plane_token",
    "verify_control_plane_token",
    "verify_internal_origin",
]
