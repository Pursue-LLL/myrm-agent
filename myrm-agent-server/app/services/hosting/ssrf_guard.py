"""SSRF guard for http_webhook outbound requests.

[POS] Block private-network and metadata endpoints before webhook deploy callbacks.

[INPUT]
- socket (POS: DNS resolution for pinned IP validation)

[OUTPUT]
- assert_safe_webhook_url: raise on disallowed host/IP targets
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFValidationError(ValueError):
    """Raised when a webhook URL fails SSRF validation."""


def validate_webhook_url(url: str, *, allow_http: bool = False) -> str:
    """Validate webhook URL is safe for server-side egress."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("https", "http"):
        raise SSRFValidationError("Webhook URL must use http or https.")
    if parsed.scheme == "http" and not allow_http:
        raise SSRFValidationError("HTTP webhooks are disabled. Use HTTPS or enable allow_http in target config.")
    host = parsed.hostname
    if not host:
        raise SSRFValidationError("Webhook URL must include a hostname.")
    lowered = host.lower()
    if lowered in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        raise SSRFValidationError("Localhost webhook URLs are not allowed.")
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFValidationError(f"Cannot resolve webhook host: {host}") from exc
    for info in addr_infos:
        ip_str = info[4][0]
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise SSRFValidationError(f"Webhook URL resolves to blocked address: {ip_str}")
    return url.strip()
