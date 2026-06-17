"""DNS rebinding protection for WebUI remote exposure.

[POS]
Host allowlist middleware for ingress and tunnel hostnames.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config.deploy_mode import is_webui_remote_mode
from app.core.infra.ingress import get_public_ingress_base_url
from app.core.security.auth.public_paths import is_public_path
from app.middleware.ingress import should_skip_ingress_rewrite
from app.remote_access.trust_zone import TrustZone, is_public_host


def _host_only(host_header: str) -> str:
    return host_header.split(":")[0].strip().lower()


def _hostname_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def build_allowed_hosts(
    public_ingress_base_url: str,
    *,
    tunnel_public_url: str = "",
) -> frozenset[str]:
    allowed = {"localhost", "127.0.0.1", "::1"}
    for url in (public_ingress_base_url, tunnel_public_url):
        hostname = _hostname_from_url(url)
        if hostname:
            allowed.add(hostname)
    return frozenset(allowed)


def is_allowed_host(host_header: str, allowed_hosts: frozenset[str]) -> bool:
    host = _host_only(host_header)
    if host in allowed_hosts:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


class HostAllowlistMiddleware(BaseHTTPMiddleware):
    """Reject unexpected Host headers on remote-exposed WebUI requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS" or is_public_path(request.url.path):
            return await call_next(request)

        trust_zone = getattr(request.state, "trust_zone", None)
        if trust_zone != TrustZone.REMOTE_EXPOSED.value and not is_webui_remote_mode():
            return await call_next(request)

        host_header = request.headers.get("host", "")
        if should_skip_ingress_rewrite(host_header):
            return await call_next(request)

        if trust_zone == TrustZone.REMOTE_EXPOSED.value and is_public_host(host_header):
            return await call_next(request)

        from app.remote_access.tunnel_manager import get_tunnel_manager

        public_url = await get_public_ingress_base_url()
        tunnel_url = get_tunnel_manager().status().public_url
        allowed = build_allowed_hosts(public_url, tunnel_public_url=tunnel_url)
        if is_allowed_host(host_header, allowed):
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Host not allowed"},
        )


__all__ = ["HostAllowlistMiddleware", "build_allowed_hosts", "is_allowed_host"]
