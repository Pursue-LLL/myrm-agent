"""SSRF guard for http_webhook outbound requests.

[POS] Block private-network and metadata endpoints before webhook deploy callbacks.

[INPUT]
- socket (POS: DNS resolution for pinned IP validation)
- myrm_agent_harness.utils.url_utils::is_blocked_ip (POS: the framework's single IP blocklist; lets the 198.18.0.0/15 range fake-IP proxies hand out for public names through)

[OUTPUT]
- validate_webhook_url: validates that a webhook URL is safe for server-side egress, raising SSRFValidationError on disallowed host/IP targets
- SSRFValidationError: raised when a webhook URL fails SSRF validation
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse

from myrm_agent_harness.utils.url_utils import is_blocked_ip


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
        ip_str = str(info[4][0])
        if is_blocked_ip(ip_str):
            raise SSRFValidationError(f"Webhook URL resolves to blocked address: {ip_str}")
    return url.strip()
