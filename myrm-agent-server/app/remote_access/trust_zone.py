"""Admission path and trust zone resolution for remote access security.

Trust decisions are driven by *how* the client reached the server, not client IP
alone. Reverse proxies and Cloudflare Tunnel terminate locally (127.0.0.1) while
the request is effectively public — ``AdmissionPath.PUBLIC_INGRESS`` captures that.

[POS]
Resolve AdmissionPath / TrustZone from request headers and ingress URL.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from enum import Enum
from urllib.parse import urlparse

from app.core.security.auth.identity import (
    _normalize_client_ip,
    is_loopback_ip,
    is_private_network_ip,
)

# Inbound platform callbacks: /api/channels/{provider}/webhook[/…]
_CHANNEL_PROVIDER_WEBHOOK_RE = re.compile(
    r"^/api/channels/[^/]+/webhook(?:/|$)",
    re.IGNORECASE,
)
_CHANNEL_PROVIDER_WEBHOOK_V1_RE = re.compile(
    r"^/api/v1/channels/[^/]+/webhook(?:/|$)",
    re.IGNORECASE,
)


class AdmissionPath(str, Enum):
    """How the HTTP/WebSocket request reached agent-server."""

    LOOPBACK_DIRECT = "loopback_direct"
    LAN_DIRECT = "lan_direct"
    PUBLIC_INGRESS = "public_ingress"
    REMOTE_BIND = "remote_bind"
    CHANNEL = "channel"
    SANDBOX_CP = "sandbox_cp"


class TrustZone(str, Enum):
    """Coarse trust bucket consumed by session policy, tool policy, and idle timeout."""

    LOCAL_TRUSTED = "local_trusted"
    REMOTE_EXPOSED = "remote_exposed"
    MANAGED = "managed"


def _host_only(host_header: str) -> str:
    return host_header.split(":")[0].strip().lower()


def is_public_host(host_header: str) -> bool:
    host = _host_only(host_header)
    if not host or host in {"localhost", "0.0.0.0"} or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (address.is_loopback or address.is_private or address.is_link_local)


def _host_matches_ingress(host_header: str, public_ingress_base_url: str) -> bool:
    if not public_ingress_base_url:
        return False
    parsed = urlparse(public_ingress_base_url)
    ingress_host = (parsed.hostname or "").lower()
    request_host = _host_only(host_header)
    if not ingress_host or not request_host:
        return False
    return request_host == ingress_host or request_host.endswith(f".{ingress_host}")


def _is_channel_webhook_path(path: str) -> bool:
    """True for inbound platform webhook/ingress callbacks, not manage API channel ids."""
    lowered = path.lower()
    # Settings manage API: /api/v1/channels/manage/{channelId}/… (channelId may be "webhook").
    if "/channels/manage/" in lowered:
        return False
    # Shared-context binding target: …/bindings/targets/channel/{targetId}.
    if "/bindings/targets/channel/" in lowered:
        return False
    if _CHANNEL_PROVIDER_WEBHOOK_RE.match(
        path
    ) or _CHANNEL_PROVIDER_WEBHOOK_V1_RE.match(path):
        return True
    return lowered.startswith("/api/v1/channels/") and "/ingress" in lowered


def has_tunnel_proxy_headers(headers: Mapping[str, str]) -> bool:
    """Return True when common reverse-proxy or tunnel headers are present."""
    for key, value in headers.items():
        if not value:
            continue
        lower_key = key.lower()
        if lower_key in {
            "cf-connecting-ip",
            "cf-ray",
            "cf-visitor",
            "x-forwarded-host",
            "x-forwarded-proto",
            "forwarded",
        }:
            return True
    return False


def _is_local_forwarded_header(value: str) -> bool:
    """True when RFC 7239 Forwarded only references loopback/local hosts."""
    for segment in value.split(","):
        segment = segment.strip()
        if not segment:
            continue
        for part in segment.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            key, raw = part.split("=", 1)
            if key.lower() not in {"for", "host"}:
                continue
            token = raw.strip().strip('"')
            if key.lower() == "for":
                host = _normalize_client_ip(token.strip("[]").split(":")[0])
                if host not in {"127.0.0.1", "localhost", "::1"}:
                    return False
            elif _host_only(token) not in {"localhost", "127.0.0.1"}:
                return False
    return True


def _is_nextjs_local_dev_proxy(headers: Mapping[str, str]) -> bool:
    """Loopback requests with only local X-Forwarded-Host (Next.js dev rewrite)."""
    forwarded_host_local = False
    external_tunnel_marker = False
    for key, value in headers.items():
        if not value:
            continue
        lower_key = key.lower()
        if lower_key == "x-forwarded-host":
            if _host_only(value) in {"localhost", "127.0.0.1"}:
                forwarded_host_local = True
        elif lower_key == "forwarded":
            if _is_local_forwarded_header(value):
                forwarded_host_local = True
            else:
                external_tunnel_marker = True
        elif lower_key == "x-forwarded-for":
            first_hop = _normalize_client_ip(
                value.split(",")[0].strip().strip("[]").split(":")[0]
            )
            if first_hop in {"127.0.0.1", "localhost", "::1"}:
                forwarded_host_local = True
        elif lower_key in {"cf-connecting-ip", "cf-ray", "cf-visitor"}:
            external_tunnel_marker = True
    return forwarded_host_local and not external_tunnel_marker


def resolve_admission_path(
    *,
    path: str,
    client_ip: str,
    host_header: str,
    headers: Mapping[str, str],
    public_ingress_base_url: str = "",
    is_sandbox: bool = False,
    is_webui_remote_mode: bool = False,
) -> AdmissionPath:
    """Classify request admission path from connection metadata."""
    if is_sandbox:
        return AdmissionPath.SANDBOX_CP

    if _is_channel_webhook_path(path):
        return AdmissionPath.CHANNEL

    loopback = is_loopback_ip(client_ip)
    private_net = is_private_network_ip(client_ip)
    public_host = is_public_host(host_header)
    ingress_match = _host_matches_ingress(host_header, public_ingress_base_url)
    tunnel_headers = has_tunnel_proxy_headers(headers)

    if public_host or ingress_match:
        return AdmissionPath.PUBLIC_INGRESS

    if loopback and tunnel_headers and not _is_nextjs_local_dev_proxy(headers):
        return AdmissionPath.PUBLIC_INGRESS

    if loopback:
        return AdmissionPath.LOOPBACK_DIRECT

    if private_net:
        return AdmissionPath.LAN_DIRECT

    if is_webui_remote_mode:
        return AdmissionPath.REMOTE_BIND

    return AdmissionPath.REMOTE_BIND


def admission_path_to_trust_zone(path: AdmissionPath) -> TrustZone:
    if path in {AdmissionPath.LOOPBACK_DIRECT, AdmissionPath.LAN_DIRECT}:
        return TrustZone.LOCAL_TRUSTED
    if path == AdmissionPath.SANDBOX_CP:
        return TrustZone.MANAGED
    return TrustZone.REMOTE_EXPOSED


def is_local_trusted_admission(path: AdmissionPath) -> bool:
    """Whether local loopback/LAN auth bypass is allowed for this admission path."""
    return admission_path_to_trust_zone(path) == TrustZone.LOCAL_TRUSTED


__all__ = [
    "AdmissionPath",
    "TrustZone",
    "admission_path_to_trust_zone",
    "has_tunnel_proxy_headers",
    "is_local_trusted_admission",
    "resolve_admission_path",
]
