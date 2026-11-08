"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- register_blocked_hostnames
- unregister_blocked_hostnames
- clear_dynamic_blocked_hostnames
- is_blocked_ip

[POS]
SSRF 黑名单、动态主机名注册与 IP 拦截；持有进程内可变黑名单状态。
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


# ============================================================================
# URL 标准化和清理
# ============================================================================


SSRF_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        # AWS
        "169.254.169.254",
        # GCP
        "metadata.google.internal",
        "metadata.google",
        "metadata",
        # 阿里云
        "100.100.100.200",
        # 腾讯云
        "metadata.tencentyun.com",
    }
)

# Hostname suffixes that resolve to internal/container networks.
# Blocks mDNS (.local), Kubernetes (.svc, .cluster.local), and home networks.
_BLOCKED_HOSTNAME_SUFFIXES = (
    ".local",
    ".localdomain",
    ".home.arpa",
    ".svc",
    ".cluster.local",
)

_DYNAMIC_BLOCKED_HOSTNAMES: set[str] = set()


def register_blocked_hostnames(*hosts: str) -> None:
    """Dynamically register additional sensitive hostnames/origins to block in SSRF checks."""
    for host in hosts:
        if not host:
            continue
        cleaned = host.strip().lower().rstrip(".")
        if cleaned:
            _DYNAMIC_BLOCKED_HOSTNAMES.add(cleaned)


def unregister_blocked_hostnames(*hosts: str) -> None:
    """Unregister previously dynamically registered sensitive hostnames."""
    for host in hosts:
        if not host:
            continue
        cleaned = host.strip().lower().rstrip(".")
        _DYNAMIC_BLOCKED_HOSTNAMES.discard(cleaned)


def clear_dynamic_blocked_hostnames() -> None:
    """Clear all dynamically registered blocked hostnames (useful for tests)."""
    _DYNAMIC_BLOCKED_HOSTNAMES.clear()


_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def is_blocked_ip(addr: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address belongs to a private/internal/reserved network.

    Uses Python's built-in ipaddress properties for comprehensive RFC coverage,
    plus explicit CGNAT check (Python's is_private doesn't cover 100.64.0.0/10).
    Exempts 198.18.0.0/15 for Fake-IP proxy compatibility (Clash, etc.).
    Handles IPv4-mapped IPv6 addresses (e.g. ::ffff:10.0.0.1).

    This is the single source of truth for all SSRF IP checks in the framework.
    Called by core.security.guards.ssrf and related outbound URL validators.
    """
    if isinstance(addr, str):
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True  # unparseable → block
    else:
        ip = addr

    v4 = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) else ip

    if (v4 or ip) in _FAKE_IP_NETWORK:
        return False

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (v4 or ip) in _CGNAT_NETWORK
    )


class _SSRFResultLike(Protocol):
    """The read-only fields of an SSRF validation result that DNS pinning reads."""

    @property
    def safe(self) -> bool: ...

    @property
    def error(self) -> str: ...

    @property
    def hostname(self) -> str: ...

    @property
    def resolved_ips(self) -> tuple[str, ...]: ...
