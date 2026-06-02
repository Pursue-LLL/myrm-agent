"""ASGI Middleware for rewriting requests with public ingress base URLs.

Fixes Webhook signature validation and OAuth callback generation in non-standard proxy environments.
"""

from urllib.parse import urlparse

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.infra.ingress import get_public_ingress_base_url


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
            # Local WebUI proxy (127.0.0.1 / localhost) must not be rewritten to a stale
            # public ingress URL when Quick Tunnel is stopped — otherwise API calls 307 away.
            host_header = next(
                (v.decode("utf-8", errors="ignore") for k, v in scope.get("headers", []) if k == b"host"),
                "",
            )
            if host_header.split(":")[0] in {"127.0.0.1", "localhost", "0.0.0.0"}:
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
