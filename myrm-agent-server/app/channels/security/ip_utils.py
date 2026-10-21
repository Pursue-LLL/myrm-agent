"""Real client IP extraction utilities.

Critical security mechanism preventing proxy bypass of rate limiting and in-flight limiter。
Validates trusted proxy chain and extracts real client IP。

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
    """Extract real client IP（ValidateTrustedProxy链）

    Security mechanism:
    1. If trusted_proxies not configured, use request.client.host directly (trust direct connection)
    2. IfConfigure了trusted_proxies，ValidateRequestWhetherfromTrustedProxy
    3.  from X-Forwarded-For in Extract最左侧 ClientIP（第一跳）

    Args:
        request: FastAPI RequestObject
        trusted_proxies: TrustedProxyIPList（SupportCIDR，如["192.168.1.0/24", "10.0.0.1"]）

    Returns:
        Real client IPString

    Example:
        >>> # Scenario1：直连（ no Proxy）
        >>> extract_real_ip(request, trusted_proxies=None)
        "203.0.113.45"  # request.client.host

        >>> # Scenario2： via NginxProxy（Trusted）
        >>> # request.client.host = "192.168.1.10" (Nginx IP)
        >>> # X-Forwarded-For = "203.0.113.45, 10.0.0.5"
        >>> extract_real_ip(request, trusted_proxies=["192.168.1.0/24"])
        "203.0.113.45"  # ExtractClientIP

        >>> # Scenario3： not TrustedProxy（拒绝信任X-Forwarded-For）
        >>> # request.client.host = "1.2.3.4" ( not yet 知IP)
        >>> extract_real_ip(request, trusted_proxies=["192.168.1.0/24"])
        "1.2.3.4"  #  using 直连IP，IgnoreX-Forwarded-For
    """
    # Get直连IP
    direct_ip = request.client.host if request.client else "unknown"

    # If not yet Configuretrusted_proxies， directly Return直连IP
    if not trusted_proxies:
        return direct_ip

    # Validate直连IPWhether is TrustedProxy
    if not _is_trusted_proxy(direct_ip, trusted_proxies):
        logger.debug(
            "Request from untrusted proxy, ignoring X-Forwarded-For",
            extra={"direct_ip": direct_ip, "trusted_proxies": trusted_proxies},
        )
        return direct_ip

    #  from X-Forwarded-ForExtractClientIP
    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if not forwarded_for:
        logger.debug(
            "Trusted proxy but no X-Forwarded-For header",
            extra={"direct_ip": direct_ip},
        )
        return direct_ip

    # X-Forwarded-ForFormat："client, proxy1, proxy2"
    # 取最左侧（最早 ClientIP）
    client_ip = forwarded_for.split(",")[0].strip()

    # ValidateExtract IPFormat
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
    """CheckIPWhether in Trusted proxy list in （SupportCIDR）"""
    if ip == "unknown":
        return False

    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for proxy_pattern in trusted_proxies:
        try:
            # 尝试Parse is CIDR
            if "/" in proxy_pattern:
                network = ipaddress.ip_network(proxy_pattern, strict=False)
                if ip_obj in network:
                    return True
            # exactIPMatch
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
    """CheckIPWhether in Blacklist in （SupportCIDR）

     for fast拦截 already 知攻击IP，成本极低。

    Args:
        ip: ClientIPAddress
        blocked_ips: IPBlacklistList（SupportCIDR，如["1.2.3.4", "10.0.0.0/8"]）

    Returns:
        True表示 in Blacklist in ， should 拦截

    Example:
        >>> if is_ip_blocked("1.2.3.4", ["1.2.3.0/24"]):
        >>>     raise WebhookResponseError(403, "blocked-ip", ...)
    """
    return _is_trusted_proxy(ip, blocked_ips)


def is_ip_allowed(ip: str, allowed_ips: Sequence[str]) -> bool:
    """CheckIPWhether in Whitelist in （SupportCIDR）

    WhitelistIP can SkipRate Limiting（如Internal监控系统）。

    Args:
        ip: ClientIPAddress
        allowed_ips: IPWhitelistList（SupportCIDR，如["192.168.1.0/24"]）

    Returns:
        True表示 in Whitelist in ， can SkipRate Limiting

    Example:
        >>> if is_ip_allowed("192.168.1.10", ["192.168.1.0/24"]):
        >>>     # SkipRate Limiting
    """
    return _is_trusted_proxy(ip, allowed_ips)


def validate_host(
    request: Request,
    allowed_hosts: Sequence[str],
) -> bool:
    """ValidateHost header（防Host Header Injection攻击）

    Purpose：mainly for  need URL变体 SignatureValidate（如Twilio）
     not  need URL变体 平台（Telegram/飞书） no 需Call此Function。

    Args:
        request: FastAPI RequestObject
        allowed_hosts: Allowed hostname list（如["api.example.com", "webhook.example.com"]）

    Returns:
        True表示Host合法，False表示非法

    Example:
        >>> # SignatureVerifierInternalCall
        >>> if not validate_host(request, ["api.example.com"]):
        >>>     raise WebhookResponseError(403, "invalid-host", ...)
    """
    host = request.headers.get("Host", "").lower()

    # 移除Port号（IfExists）
    if ":" in host:
        host = host.split(":")[0]

    return host in [h.lower() for h in allowed_hosts]
