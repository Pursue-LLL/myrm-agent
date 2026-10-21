"""Verify HMAC-signed requests from the external control-service reverse proxy.

[INPUT]
- app.config.settings::internal_service_key (POS: INTERNAL_SERVICE_KEY env from CP injection)

[OUTPUT]
- verify_cp_proxy_request: validated user_id or None

[POS]
Sandbox-mode trust boundary for CP-proxied HTTP/WebSocket traffic (replaces bare X-User-Id).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping

from app.config.settings import settings

HEADER_USER_ID = "X-User-Id"
HEADER_TIMESTAMP = "X-CP-Timestamp"
HEADER_SIGNATURE = "X-CP-Signature"

_SIGNATURE_MAX_SKEW_SECONDS = 300


def _header_value(headers: Mapping[str, str], name: str) -> str:
    lower_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value.strip()
    return ""


def normalize_upstream_path(path: str) -> str:
    """Normalize request path for stable signature verification."""
    normalized = path if path.startswith("/") else f"/{path}"
    if len(normalized) > 1 and normalized.endswith("/"):
        return normalized.rstrip("/")
    return normalized


def compute_proxy_signature(
    internal_service_key: str,
    *,
    timestamp: str,
    user_id: str,
    method: str,
    path: str,
) -> str:
    """Compute HMAC-SHA256 hex digest (must match CP gateway.cp_proxy_auth)."""
    payload = f"{timestamp}\n{user_id}\n{method.upper()}\n{normalize_upstream_path(path)}"
    return hmac.new(
        internal_service_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_signed_proxy_headers(
    *,
    user_id: str,
    method: str,
    path: str,
    internal_service_key: str,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Build signed headers (mirrors CP gateway.cp_proxy_auth for tests)."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    signature = compute_proxy_signature(
        internal_service_key,
        timestamp=ts,
        user_id=user_id,
        method=method,
        path=path,
    )
    return {
        HEADER_USER_ID: user_id,
        HEADER_TIMESTAMP: ts,
        HEADER_SIGNATURE: signature,
    }


def verify_cp_proxy_request(
    headers: Mapping[str, str],
    *,
    method: str,
    path: str,
) -> str | None:
    """Return authenticated user_id when CP proxy signature is valid."""
    service_key = settings.internal_service_key.get_secret_value()
    if not service_key:
        return None

    user_id = _header_value(headers, HEADER_USER_ID)
    timestamp_raw = _header_value(headers, HEADER_TIMESTAMP)
    signature = _header_value(headers, HEADER_SIGNATURE)
    if not user_id or not timestamp_raw or not signature:
        return None

    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        return None

    now = int(time.time())
    if abs(now - timestamp) > _SIGNATURE_MAX_SKEW_SECONDS:
        return None

    expected = compute_proxy_signature(
        service_key,
        timestamp=timestamp_raw,
        user_id=user_id,
        method=method,
        path=path,
    )
    if not hmac.compare_digest(expected, signature):
        return None
    return user_id


__all__ = [
    "HEADER_SIGNATURE",
    "HEADER_TIMESTAMP",
    "HEADER_USER_ID",
    "build_signed_proxy_headers",
    "compute_proxy_signature",
    "normalize_upstream_path",
    "verify_cp_proxy_request",
]
