"""Real client IP extraction utilities.

Critical security mechanism preventing proxy bypass of rate limiting and in-flight limiter.
Validates trusted proxy chain and extracts real client IP.

[INPUT]
- fastapi::Request (POS: Out-of-the-box FastAPI implementation. Users can directly use these classes without implementing RouteRegistrar Protocol themselves.)

[OUTPUT]
- extract_real_ip(): Extract real client IP
- validate_host(): Host header validation utility

[POS]
IP extraction utility layer. Provides trusted proxy validation and real IP extraction,
preventing X-Forwarded-For header spoofing attacks.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Sequence

from fastapi import Request

logger = logging.getLogger(__name__)


def extract_real_ip(
    request: Request,
    trusted_proxies: Sequence[str] | None = None,
) -> str:
    """Extract the real client IP (validating the trusted proxy chain)

    Security mechanism:
    1. If trusted_proxies not configured, use request.client.host directly (trust direct connection)
    2. If trusted_proxies is configured, validate that the request comes from a trusted proxy
    3. Extract the leftmost client IP (the first hop) from X-Forwarded-For

    Args:
        request: FastAPI request object
        trusted_proxies: Trusted proxy IP list (CIDR supported, e.g. ["192.168.1.0/24", "10.0.0.1"])

    Returns:
        Real client IP string

    Example:
        >>> # Scenario 1: direct connection (no proxy)
        >>> extract_real_ip(request, trusted_proxies=None)
        "203.0.113.45"  # request.client.host

        >>> # Scenario 2: via an Nginx proxy (trusted)
        >>> # request.client.host = "192.168.1.10" (Nginx IP)
        >>> # X-Forwarded-For = "203.0.113.45, 10.0.0.5"
        >>> extract_real_ip(request, trusted_proxies=["192.168.1.0/24"])
        "203.0.113.45"  # Extracted client IP

        >>> # Scenario 3: untrusted proxy (X-Forwarded-For is not trusted)
        >>> # request.client.host = "1.2.3.4" (unknown IP)
        >>> extract_real_ip(request, trusted_proxies=["192.168.1.0/24"])
        "1.2.3.4"  # Uses the direct IP and ignores X-Forwarded-For
    """
    # Get the direct connection IP
    direct_ip = request.client.host if request.client else "unknown"

    # Without configured trusted_proxies, return the direct connection IP
    if not trusted_proxies:
        return direct_ip

    # Validate that the direct connection IP is a trusted proxy
    if not _is_trusted_proxy(direct_ip, trusted_proxies):
        logger.debug(
            "Request from untrusted proxy, ignoring X-Forwarded-For",
            extra={"direct_ip": direct_ip, "trusted_proxies": trusted_proxies},
        )
        return direct_ip

    # Extract the client IP from X-Forwarded-For
    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if not forwarded_for:
        logger.debug(
            "Trusted proxy but no X-Forwarded-For header",
            extra={"direct_ip": direct_ip},
        )
        return direct_ip

    # X-Forwarded-For format: "client, proxy1, proxy2"
    # Take the leftmost entry (the earliest client IP)
    client_ip = forwarded_for.split(",")[0].strip()

    # Validate the format of the extracted IP
    try:
        ipaddress.ip_address(client_ip)
        logger.debug(
            "Extracted real IP from X-Forwarded-For",
            extra={"real_ip": client_ip, "forwarded_for": forwarded_for},
        )
        return client_ip
    except ValueError:
        logger.warning(
            "Invalid IP in X-Forwarded-For, fallback to direct IP",
            extra={"invalid_ip": client_ip, "direct_ip": direct_ip},
        )
        return direct_ip


def _is_trusted_proxy(ip: str, trusted_proxies: Sequence[str]) -> bool:
    """Check whether the IP is in the trusted proxy list (CIDR supported)."""
    if ip == "unknown":
        return False

    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for proxy_pattern in trusted_proxies:
        try:
            # Try to parse it as a CIDR
            if "/" in proxy_pattern:
                network = ipaddress.ip_network(proxy_pattern, strict=False)
                if ip_obj in network:
                    return True
            # Exact IP match
            elif ip_obj == ipaddress.ip_address(proxy_pattern):
                return True
        except ValueError:
            logger.warning(
                f"Invalid trusted proxy pattern: {proxy_pattern}",
                extra={"pattern": proxy_pattern},
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
    return _is_trusted_proxy(ip, blocked_ips)


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
    return _is_trusted_proxy(ip, allowed_ips)


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
