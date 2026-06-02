"""Shared request identity resolution for HTTP and WebSocket scopes.

[INPUT]
- app.config.settings (POS: SANDBOX_API_KEY, INTERNAL_SERVICE_KEY)
- app.platform_utils.deployment_capabilities (POS: deploy-mode capability flags)
- app.core.security.auth.public_paths (POS: unauthenticated path whitelist)
- app.core.security.auth.cp_proxy (POS: CP HMAC proxy signature verification)

[OUTPUT]
- resolve_identity, resolve_identity_from_http_scope, resolve_identity_from_ws_scope

[POS]
Single identity resolver consumed by HTTP AuthMiddleware and WsAuthMiddleware.
"""

from __future__ import annotations

import hmac
import ipaddress
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from app.config.settings import settings

LOCAL_USER_ID: Final[str] = "local-user"
SANDBOX_FALLBACK_USER_ID: Final[str] = "sandbox"

_LOOPBACK_NETS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)

_PRIVATE_NETS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    """Authentication outcome for a single HTTP or WebSocket request."""

    user_id: str | None
    auth_source: str | None
    client_ip: str
    loopback: bool
    private_net: bool


def _ip_in_networks(
    ip_str: str,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    if not ip_str:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def is_loopback_ip(client_ip: str) -> bool:
    return _ip_in_networks(client_ip, _LOOPBACK_NETS)


def is_private_network_ip(client_ip: str) -> bool:
    return _ip_in_networks(client_ip, _PRIVATE_NETS)


def _header_value(headers: Mapping[str, str], name: str) -> str:
    lower_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value.strip()
    return ""


def _headers_from_scope(raw_headers: Sequence[tuple[bytes, bytes]]) -> dict[str, str]:
    decoded: dict[str, str] = {}
    for key_bytes, value_bytes in raw_headers:
        key = key_bytes.decode("latin-1")
        decoded[key] = value_bytes.decode("latin-1")
    return decoded


def _client_ip_from_scope(client: tuple[str, int] | None) -> str:
    if client:
        return client[0]
    return ""


def _extract_bearer_token(headers: Mapping[str, str]) -> str | None:
    auth_header = _header_value(headers, "Authorization")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        return token or None
    return None


def _extract_sandbox_api_key(headers: Mapping[str, str]) -> str | None:
    header_key = _header_value(headers, "X-Sandbox-Api-Key")
    if header_key:
        return header_key
    return _extract_bearer_token(headers)


def _verify_sandbox_api_key(provided: str) -> bool:
    expected = settings.sandbox_api_key.get_secret_value()
    if not expected:
        return False
    return hmac.compare_digest(provided, expected)


def resolve_identity(
    *,
    path: str,
    method: str,
    headers: Mapping[str, str],
    client_ip: str,
) -> ResolvedIdentity:
    """Resolve user identity from HTTP or WebSocket request metadata."""
    from app.core.security.auth.public_paths import is_public_path
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    loopback = is_loopback_ip(client_ip)
    private_net = is_private_network_ip(client_ip)

    if method == "OPTIONS" or is_public_path(path):
        return ResolvedIdentity(
            user_id=None,
            auth_source=None,
            client_ip=client_ip,
            loopback=loopback,
            private_net=private_net,
        )

    caps = get_deployment_capabilities()
    user_id: str | None = None
    auth_source: str | None = None

    if caps.is_sandbox_instance:
        from app.core.security.auth.cp_proxy import verify_cp_proxy_request

        verified_user = verify_cp_proxy_request(headers, method=method, path=path)
        if verified_user:
            user_id = verified_user
            auth_source = "cp_proxy"
        else:
            api_key = _extract_sandbox_api_key(headers)
            if api_key and _verify_sandbox_api_key(api_key):
                user_id = _header_value(headers, "X-User-Id") or SANDBOX_FALLBACK_USER_ID
                auth_source = "sandbox_api_key"
            elif loopback:
                user_id = SANDBOX_FALLBACK_USER_ID
                auth_source = "loopback"
    elif caps.allows_local_skills:
        if loopback or private_net:
            user_id = LOCAL_USER_ID
            auth_source = "loopback"
        elif caps.requires_api_key_auth:
            api_key = _extract_sandbox_api_key(headers)
            if api_key and _verify_sandbox_api_key(api_key):
                user_id = LOCAL_USER_ID
                auth_source = "sandbox_api_key"
    elif loopback:
        user_id = LOCAL_USER_ID
        auth_source = "loopback"

    return ResolvedIdentity(
        user_id=user_id,
        auth_source=auth_source,
        client_ip=client_ip,
        loopback=loopback,
        private_net=private_net,
    )


def resolve_identity_from_http_scope(scope: dict[str, object]) -> ResolvedIdentity:
    """Resolve identity from a Starlette HTTP ASGI scope."""
    headers = _headers_from_scope(scope.get("headers", []))  # type: ignore[arg-type]
    client = scope.get("client")
    client_ip = _client_ip_from_scope(client if isinstance(client, tuple) else None)
    path = str(scope.get("path", ""))
    method = str(scope.get("method", "GET"))
    return resolve_identity(path=path, method=method, headers=headers, client_ip=client_ip)


def resolve_identity_from_ws_scope(scope: dict[str, object]) -> ResolvedIdentity:
    """Resolve identity from a Starlette WebSocket ASGI scope."""
    headers = _headers_from_scope(scope.get("headers", []))  # type: ignore[arg-type]
    client = scope.get("client")
    client_ip = _client_ip_from_scope(client if isinstance(client, tuple) else None)
    path = str(scope.get("path", ""))
    return resolve_identity(path=path, method="GET", headers=headers, client_ip=client_ip)


__all__ = [
    "LOCAL_USER_ID",
    "SANDBOX_FALLBACK_USER_ID",
    "ResolvedIdentity",
    "is_loopback_ip",
    "is_private_network_ip",
    "resolve_identity",
    "resolve_identity_from_http_scope",
    "resolve_identity_from_ws_scope",
]
