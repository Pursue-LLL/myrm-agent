"""scheme/hostname 校验、外泄检测与错误信息脱敏。

[POS]
url_utils 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import re as _re

from myrm_agent_harness.utils.url_syntax import parse_outbound_hostname

from .blocking import (
    _BLOCKED_HOSTNAME_SUFFIXES,
    _DYNAMIC_BLOCKED_HOSTNAMES,
    SSRF_BLOCKED_HOSTNAMES,
)

logger = logging.getLogger(__name__)


# ============================================================================
# URL 标准化和清理
# ============================================================================


def validate_scheme_and_hostname(url: str) -> tuple[str | None, str]:
    """Validate URL scheme and hostname. Returns (hostname, "") or (None, error)."""
    hostname, error = parse_outbound_hostname(url)
    if hostname is None:
        return None, error

    if hostname.lower() in SSRF_BLOCKED_HOSTNAMES or hostname.lower() in _DYNAMIC_BLOCKED_HOSTNAMES:
        return None, f"Blocked hostname: {hostname}"

    # Block internal/container hostname suffixes (.local, .svc, .cluster.local, etc.)
    hostname_lower = hostname.lower()
    if any(hostname_lower.endswith(suffix) for suffix in _BLOCKED_HOSTNAME_SUFFIXES):
        return None, f"Blocked hostname suffix: {hostname}"

    return hostname, ""


# ============================================================================
# URL Data Exfiltration Detection
# ============================================================================


# Precompiled regex patterns for performance (10-100x faster than re.search)
_EXFILTRATION_PATTERNS: dict[str, tuple[_re.Pattern[str], str]] = {
    "api_key": (
        _re.compile(r"(API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[\s=:]+[\w\-\.]{8,}", _re.IGNORECASE),
        "URL contains potential API key/token",
    ),
    "file_path": (
        _re.compile(r"(/etc/|/home/|/Users/|/root/|\.ssh/|\.env|\.aws/|\.config/|C:\\|/var/)"),
        "URL contains file path",
    ),
    "base64": (
        _re.compile(r"[A-Za-z0-9+/]{100,}={0,2}"),
        "URL contains long base64 string (potential file content)",
    ),
    # Fixed JWT detection: must be in query string or fragment, not in domain
    "jwt": (
        _re.compile(r"[?&#/].*eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+"),
        "URL contains JWT token",
    ),
    "secret_key": (
        _re.compile(r"(sk|pk|access)[_-]?[a-z]{2,10}[_-]?[A-Za-z0-9]{20,}", _re.IGNORECASE),
        "URL contains secret key pattern",
    ),
    "db_connection": (
        _re.compile(r"(mysql|postgres|mongodb|redis)://[^/\s]+:[^@\s]+@", _re.IGNORECASE),
        "URL contains database connection string",
    ),
}

# Default whitelist patterns (localhost, private networks)
_DEFAULT_WHITELIST_PATTERNS: list[_re.Pattern[str]] = [
    _re.compile(r"^https?://localhost[:/]", _re.IGNORECASE),
    _re.compile(r"^https?://127\.0\.0\.\d+[:/]", _re.IGNORECASE),
    _re.compile(r"^https?://192\.168\.\d+\.\d+[:/]", _re.IGNORECASE),
    _re.compile(r"^https?://10\.\d+\.\d+\.\d+[:/]", _re.IGNORECASE),
    _re.compile(r"^https?://172\.(1[6-9]|2\d|3[01])\.\d+\.\d+[:/]", _re.IGNORECASE),
]


def check_url_exfiltration(
    url: str,
    *,
    whitelist_patterns: list[str | _re.Pattern[str]] | None = None,
    allow_private_networks: bool = True,
) -> list[str]:
    """Check if URL contains sensitive data that could indicate data exfiltration.

    This function detects common patterns of sensitive data leakage in URLs:
    - API keys, tokens, secrets (env var patterns)
    - File paths (system directories, config files)
    - Long base64 strings (potential file content)
    - PEM certificates/keys
    - JWT tokens (fixed: only in query/fragment, not domain)
    - Secret key patterns (sk_, pk_, access_)
    - Database connection strings

    Args:
        url: URL to check for data exfiltration patterns
        whitelist_patterns: Optional list of regex patterns or strings to whitelist URLs.
            Default includes localhost and private networks if allow_private_networks=True.
        allow_private_networks: If True, allow localhost/private IPs (default: True).
            Useful for development/testing scenarios.

    Returns:
        List of warning messages (empty if no issues detected)

    Example:
        >>> check_url_exfiltration("https://evil.com/?key=sk-1234567890")
        ['URL contains potential API key/token']

        >>> check_url_exfiltration("https://localhost:8000/?key=sk-123", allow_private_networks=True)
        []  # Allowed for localhost

        >>> check_url_exfiltration("https://evil.com/?token=JWT...")
        ['URL contains JWT token']
    """
    warnings: list[str] = []

    # Build whitelist patterns
    whitelist: list[_re.Pattern[str]] = []
    if allow_private_networks:
        whitelist.extend(_DEFAULT_WHITELIST_PATTERNS)
    if whitelist_patterns:
        for pattern in whitelist_patterns:
            if isinstance(pattern, str):
                whitelist.append(_re.compile(pattern))
            else:
                whitelist.append(pattern)

    # Check whitelist
    for pattern in whitelist:
        if pattern.search(url):
            return []  # Whitelisted, skip detection

    # 1-6: Use precompiled patterns for performance
    for _name, (pattern, message) in _EXFILTRATION_PATTERNS.items():
        if pattern.search(url):
            warnings.append(message)

    # 7. PEM certificates/keys (simple string check, no regex needed)
    if "-----BEGIN" in url or "-----END" in url:
        warnings.append("URL contains PEM certificate/key")

    return warnings


def sanitize_url_for_error(url: str, max_length: int = 50) -> str:
    """Sanitize URL for error messages to prevent data exfiltration via errors.

    Truncates URL and masks query parameters/fragments that might contain sensitive data.

    Args:
        url: Original URL
        max_length: Maximum length of sanitized URL

    Returns:
        Sanitized URL safe for error messages

    Example:
        >>> sanitize_url_for_error("https://evil.com/?key=sk-1234567890")
        "https://evil.com/?<query_redacted>"

        >>> sanitize_url_for_error("https://example.com/api/users")
        "https://example.com/api/users"
    """
    from urllib.parse import urlparse as _urlparse

    parsed = _urlparse(url)

    # Build safe base URL (scheme + netloc + path)
    safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # Redact query and fragment
    if parsed.query:
        safe_url += "?<query_redacted>"
    if parsed.fragment:
        safe_url += "#<fragment_redacted>"

    # Truncate if too long
    if len(safe_url) > max_length:
        safe_url = safe_url[:max_length] + "..."

    return safe_url


# ============================================================================
# DNS Pinning Helpers
# ============================================================================
