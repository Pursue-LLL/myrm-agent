"""Shared request identity resolution for HTTP and WebSocket scopes.

[INPUT]
- app.config.settings (POS: SANDBOX_API_KEY, INTERNAL_SERVICE_KEY)
- app.platform_utils.deployment_capabilities (POS: deploy-mode capability flags)
- app.core.security.auth.public_paths (POS: unauthenticated path whitelist)
- app.core.security.auth.cp_proxy (POS: CP HMAC proxy signature verification)

[OUTPUT]
- resolve_identity, resolve_identity_from_http_scope, resolve_identity_from_ws_scope
- webui_session auth_source when local API protection is enabled

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
    local_trusted: bool = True
    admission_path: str | None = None
    trust_zone: str | None = None
    session_username: str | None = None
    pair_bound_chat_id: str | None = None


def _normalize_client_ip(ip_str: str) -> str:
    """Unwrap IPv4-mapped IPv6 (e.g. Node.js ::ffff:127.0.0.1) for loopback checks."""
    if not ip_str:
        return ip_str
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return ip_str
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return ip_str


def _ip_in_networks(
    ip_str: str,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    normalized = _normalize_client_ip(ip_str)
    if not normalized:
        return False
    try:
        ip = ipaddress.ip_address(normalized)
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
    admission_path: str | None = None,
    trust_zone: str | None = None,
    local_trusted: bool | None = None,
    query_string: str = "",
    pair_token_override: str | None = None,
) -> ResolvedIdentity:
    """Resolve user identity from HTTP or WebSocket request metadata."""
    from app.core.security.auth.public_paths import is_public_path
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities
    from app.remote_access.trust_zone import (
        AdmissionPath,
        TrustZone,
        admission_path_to_trust_zone,
        is_local_trusted_admission,
        resolve_admission_path,
    )

    loopback = is_loopback_ip(client_ip)
    private_net = is_private_network_ip(client_ip)

    if admission_path is None:
        from app.config.deploy_mode import is_sandbox, is_webui_remote_mode

        resolved_path = resolve_admission_path(
            path=path,
            client_ip=client_ip,
            host_header=_header_value(headers, "Host"),
            headers=headers,
            is_sandbox=is_sandbox(),
            is_webui_remote_mode=is_webui_remote_mode(),
        )
        admission_path = resolved_path.value
        trust_zone = admission_path_to_trust_zone(resolved_path).value
        local_trusted = is_local_trusted_admission(resolved_path)
    elif local_trusted is None:
        local_trusted = is_local_trusted_admission(AdmissionPath(admission_path))
        if trust_zone is None:
            trust_zone = admission_path_to_trust_zone(AdmissionPath(admission_path)).value

    identity_meta = {
        "local_trusted": local_trusted,
        "admission_path": admission_path,
        "trust_zone": trust_zone,
    }

    if method == "OPTIONS" or is_public_path(path):
        return ResolvedIdentity(
            user_id=None,
            auth_source=None,
            client_ip=client_ip,
            loopback=loopback,
            private_net=private_net,
            **identity_meta,
        )

    caps = get_deployment_capabilities()
    user_id: str | None = None
    auth_source: str | None = None
    session_username: str | None = None
    pair_bound_chat_id: str | None = None

    from app.services.webui.session import REMOTE_IDLE_TTL_SECONDS

    max_idle_seconds = None if local_trusted else REMOTE_IDLE_TTL_SECONDS

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
        from app.services.webui.access_policy import (
            local_api_requires_session,
            resolve_webui_session_username,
        )

        session_user = resolve_webui_session_username(headers, max_idle_seconds=max_idle_seconds)
        protected = local_api_requires_session()
        if session_user and protected:
            user_id = LOCAL_USER_ID
            auth_source = "webui_session"
            session_username = session_user
        elif trust_zone == TrustZone.REMOTE_EXPOSED.value:
            from app.remote_access.mobile_gate import (
                extract_pair_token,
                is_e2ee_bootstrap_path,
                is_mobile_remote_control_path,
                is_mobile_remote_pairing_path,
                pair_token_authorizes_path,
            )

            if is_e2ee_bootstrap_path(path):
                user_id = LOCAL_USER_ID
                auth_source = "e2ee_bootstrap"
            else:
                pair_token = pair_token_override or extract_pair_token(headers, query_string)
                mobile_pair_path = is_mobile_remote_control_path(path) or is_mobile_remote_pairing_path(path)
                if mobile_pair_path and pair_token_authorizes_path(pair_token, path):
                    user_id = LOCAL_USER_ID
                    auth_source = "pair_token"
                    from app.remote_access.pairing import parse_pairing_token

                    parsed = parse_pairing_token(pair_token)
                    if parsed is not None:
                        bound = parsed.get("chat_id")
                        if isinstance(bound, str):
                            pair_bound_chat_id = bound
        elif local_trusted and (loopback or (private_net and not protected)):
            user_id = LOCAL_USER_ID
            auth_source = "loopback"
        elif caps.requires_api_key_auth:
            api_key = _extract_sandbox_api_key(headers)
            if api_key and _verify_sandbox_api_key(api_key):
                user_id = LOCAL_USER_ID
                auth_source = "sandbox_api_key"
    elif local_trusted and loopback:
        user_id = LOCAL_USER_ID
        auth_source = "loopback"

    return ResolvedIdentity(
        user_id=user_id,
        auth_source=auth_source,
        client_ip=client_ip,
        loopback=loopback,
        private_net=private_net,
        session_username=session_username,
        pair_bound_chat_id=pair_bound_chat_id,
        **identity_meta,
    )


def resolve_identity_from_http_scope(scope: dict[str, object]) -> ResolvedIdentity:
    """Resolve identity from a Starlette HTTP ASGI scope."""
    headers = _headers_from_scope(scope.get("headers", []))  # type: ignore[arg-type]
    client = scope.get("client")
    client_ip = _client_ip_from_scope(client if isinstance(client, tuple) else None)
    path = str(scope.get("path", ""))
    method = str(scope.get("method", "GET"))
    query_string = str(scope.get("query_string", b""), "latin-1")
    return resolve_identity(
        path=path,
        method=method,
        headers=headers,
        client_ip=client_ip,
        query_string=query_string,
    )


def resolve_identity_from_ws_scope(scope: dict[str, object]) -> ResolvedIdentity:
    """Resolve identity from a Starlette WebSocket ASGI scope."""
    headers = _headers_from_scope(scope.get("headers", []))  # type: ignore[arg-type]
    client = scope.get("client")
    client_ip = _client_ip_from_scope(client if isinstance(client, tuple) else None)
    path = str(scope.get("path", ""))
    query_string = str(scope.get("query_string", b""), "latin-1")
    return resolve_identity(
        path=path,
        method="GET",
        headers=headers,
        client_ip=client_ip,
        query_string=query_string,
    )


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
