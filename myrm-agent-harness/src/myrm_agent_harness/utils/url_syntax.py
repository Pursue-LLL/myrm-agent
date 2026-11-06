"""Syntax check for outbound URLs, independent of any hostname blocklist.

[INPUT]
- urllib.parse::urlparse (POS: stdlib URL parsing)

[OUTPUT]
- SSRF_ALLOWED_SCHEMES: schemes an outbound request may use
- parse_outbound_hostname(): (hostname, "") or (None, error)

[POS]
Shared by every outbound-URL policy, including the ones that admit private hosts (local mode) and
therefore have no hostname blocklist: the parser-divergence defence (confusing characters and
percent-encoded hosts) and the scheme allowlist must not depend on which blocklist a policy brings.
"""

from __future__ import annotations

from urllib.parse import urlparse

SSRF_ALLOWED_SCHEMES = frozenset({"http", "https", "ws", "wss"})

# Parser-confusing characters that cause urlparse/HTTP client divergence.
# Attackers inject these to bypass hostname extraction (CVE-class SSRF bypass).
_PARSER_CONFUSING_CHARS = frozenset("\\\t\n\r")


def parse_outbound_hostname(url: str) -> tuple[str | None, str]:
    """Syntax check for an outbound URL. Returns (hostname, "") or (None, error)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None, "Malformed URL"

    # e.g. http://evil.com\t@169.254.169.254/ — tab makes urlparse extract the wrong hostname.
    if any(c in _PARSER_CONFUSING_CHARS for c in url):
        return None, "URL contains parser-confusing characters"

    scheme = (parsed.scheme or "").lower()
    if scheme not in SSRF_ALLOWED_SCHEMES:
        return None, f"Blocked URL scheme: {scheme}"

    hostname = parsed.hostname
    if not hostname:
        return None, "Missing hostname"

    # An HTTP client percent-decodes a host before dialing it (127%2e0%2e0%2e1 reaches 127.0.0.1) while the
    # classifiers read the raw text. An IPv6 literal is the only host that holds a ':' and the only one
    # whose zone id (fe80::1%25en0) legitimately keeps a '%'.
    if "%" in hostname and ":" not in hostname:
        return None, "Hostname contains percent-encoding"

    # Normalize trailing dot (FQDN: "localhost." -> "localhost") to match blocklists.
    return hostname.rstrip("."), ""
