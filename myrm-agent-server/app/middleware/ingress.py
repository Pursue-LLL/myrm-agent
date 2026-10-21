"""ASGI Middleware for rewriting requests with public ingress base URLs.

Fixes Webhook signature validation and OAuth callback generation in non-standard proxy environments.
"""

import ipaddress
from urllib.parse import urlparse

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.infra.ingress import get_public_ingress_base_url


def should_skip_ingress_rewrite(host_header: str) -> bool:
    """Return True when the request targets loopback or a private LAN host.

    Local WebUI and same-network access must not be rewritten to a configured
    public Ingress URL; otherwise API calls resolve to an unreachable public host.
    """
    host_only = host_header.split(":")[0].strip().lower()
    if host_only in {"localhost", "0.0.0.0"} or host_only.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host_only)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


class PublicIngressMiddleware:
    """Rewrite HTTP scope using the explicit Public Ingress URL.

    Replaces the scheme and Host header in the ASGI scope to ensure downstream Request
    objects compute the correct absolute URL, fixing OAuth redirects and signature hashing.
    """

    def __init__(self, app: ASGIApp, prefix: str = "/api/") -> None:
        """Initialize middleware.

        Args:
            app: The ASGI app.
            prefix: Only rewrite scope for paths starting with this prefix.
        """
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process ASGI request."""
        if scope["type"] == "http" and scope["path"].startswith(self.prefix):
            host_header = next(
                (v.decode("utf-8", errors="ignore") for k, v in scope.get("headers", []) if k == b"host"),
                "",
            )
            if should_skip_ingress_rewrite(host_header):
                await self.app(scope, receive, send)
                return

            public_url_str = await get_public_ingress_base_url()
            if public_url_str:
                parsed = urlparse(public_url_str)

                # Rewrite scheme
                scope["scheme"] = parsed.scheme

                # Rewrite Host header
                headers = scope.get("headers", [])
                new_headers = [(k, v) for k, v in headers if k != b"host"]
                new_headers.append((b"host", parsed.netloc.encode("utf-8")))
                scope["headers"] = new_headers

                # Rewrite server tuple
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                scope["server"] = (parsed.hostname or "", port)

        await self.app(scope, receive, send)
