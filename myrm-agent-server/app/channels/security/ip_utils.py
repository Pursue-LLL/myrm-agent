"""IP list matching and Host header validation utilities.

[INPUT]
- fastapi::Request (POS: Out-of-the-box FastAPI implementation. Users can directly use these classes without implementing RouteRegistrar Protocol themselves.)

[OUTPUT]
- is_ip_blocked(): IP blocklist check (CIDR supported)
- is_ip_allowed(): IP allowlist check (CIDR supported)
- validate_host(): Host header validation utility

[POS]
IP utility layer. Matches a client address against allow/deny lists and validates Host headers.
The address itself comes from ``app.core.security.client_address::client_ip``; nothing here reads
X-Forwarded-For or X-Real-IP, which a visitor can forge.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Sequence

from fastapi import Request

logger = logging.getLogger(__name__)


def _matches_any(ip: str, patterns: Sequence[str]) -> bool:
    """Check whether the IP matches any exact address or CIDR network in patterns (a non-address never matches)."""
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for pattern in patterns:
        try:
            # Try to parse it as a CIDR
            if "/" in pattern:
                network = ipaddress.ip_network(pattern, strict=False)
                if ip_obj in network:
                    return True
            # Exact IP match
            elif ip_obj == ipaddress.ip_address(pattern):
                return True
        except ValueError:
            logger.warning(
                f"Invalid IP pattern: {pattern}",
                extra={"pattern": pattern},
            )
            continue

    return False


def is_ip_blocked(ip: str, blocked_ips: Sequence[str]) -> bool:
    """Check whether the IP is in the blocklist (CIDR supported)

    Used to block known attacking IPs quickly at very low cost.

    Args:
        ip: Client IP address
        blocked_ips: IP blocklist (CIDR supported, e.g. ["1.2.3.4", "10.0.0.0/8"])

    Returns:
        True if the IP is in the blocklist and should be blocked

    Example:
        >>> if is_ip_blocked("1.2.3.4", ["1.2.3.0/24"]):
        >>>     raise WebhookResponseError(403, "blocked-ip", ...)
    """
    return _matches_any(ip, blocked_ips)


def is_ip_allowed(ip: str, allowed_ips: Sequence[str]) -> bool:
    """Check whether the IP is in the allowlist (CIDR supported)

    Allowlisted IPs can skip rate limiting (e.g. internal monitoring systems).

    Args:
        ip: Client IP address
        allowed_ips: IP allowlist (CIDR supported, e.g. ["192.168.1.0/24"])

    Returns:
        True if the IP is in the allowlist and can skip rate limiting

    Example:
        >>> if is_ip_allowed("192.168.1.10", ["192.168.1.0/24"]):
        >>>     # Skip rate limiting
    """
    return _matches_any(ip, allowed_ips)


def validate_host(
    request: Request,
    allowed_hosts: Sequence[str],
) -> bool:
    """Validate the Host header (guards against Host header injection attacks)

    Purpose: mainly for platforms whose signature validation needs the URL variant (e.g. Twilio).
    Platforms that do not need the URL variant (Telegram/Feishu) do not need to call this function.

    Args:
        request: FastAPI request object
        allowed_hosts: Allowed hostname list (e.g. ["api.example.com", "webhook.example.com"])

    Returns:
        True if the Host is valid, False otherwise

    Example:
        >>> # Called inside the signature verifier
        >>> if not validate_host(request, ["api.example.com"]):
        >>>     raise WebhookResponseError(403, "invalid-host", ...)
    """
    host = request.headers.get("Host", "").lower()

    # Strip the port number (if present)
    if ":" in host:
        host = host.split(":")[0]

    return host in [h.lower() for h in allowed_hosts]
