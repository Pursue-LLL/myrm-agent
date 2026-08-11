"""Extension tab access policy — single source of truth for relay and REST filters.

[INPUT]
- Tab URL, domain, tab_id (POS: extension-reported tab metadata)

[OUTPUT]
- ExtensionAccessPolicy: user-configured access boundaries
- is_tab_accessible, is_policy_valid_for_automation, is_internal_browser_url
- prune_paused_tab_ids

[POS]
Shared policy evaluation for ExtensionBridgeService list_tabs, relay sync, and
connect paths. Keeps server-side filtering consistent (fail-closed by default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(slots=True)
class ExtensionAccessPolicy:
    """User-controlled boundaries for which Chrome tabs the agent may control."""

    allow_all_eligible_tabs: bool = False
    authorized_domains: list[str] = field(default_factory=list)
    paused_tab_ids: frozenset[int] = frozenset()


def normalize_domain_patterns(domains: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in domains:
        pattern = raw.strip().lower().rstrip(".")
        if not pattern or pattern in seen:
            continue
        seen.add(pattern)
        normalized.append(pattern)
    return normalized


def match_domain(domain: str, patterns: list[str]) -> bool:
    """Match *domain* against allowlist patterns (supports ``*.example.com``)."""
    domain_lower = domain.strip().lower().rstrip(".")
    if not domain_lower:
        return False
    for pattern in patterns:
        if pattern == domain_lower:
            return True
        if pattern.startswith("*."):
            suffix = pattern[2:]
            if suffix and (domain_lower == suffix or domain_lower.endswith(f".{suffix}")):
                return True
    return False


def is_internal_browser_url(url: str) -> bool:
    """Return True for Chrome-internal URLs that must never enter the relay."""
    trimmed = (url or "").strip()
    if not trimmed:
        return True
    lowered = trimmed.lower()
    if lowered in {"about:blank", "about:newtab"}:
        return False
    internal_prefixes = (
        "chrome://",
        "chrome-extension://",
        "devtools://",
        "edge://",
        "brave://",
    )
    return lowered.startswith(internal_prefixes)


def is_eligible_http_url(url: str) -> bool:
    """Ordinary web pages the extension may control when allow-all is enabled."""
    trimmed = (url or "").strip()
    if not trimmed or is_internal_browser_url(trimmed):
        return False
    try:
        parsed = urlparse(trimmed)
    except ValueError:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https", "file"}:
        return False
    host = (parsed.hostname or "").strip()
    return bool(host) or scheme == "file"


def is_policy_valid_for_automation(policy: ExtensionAccessPolicy) -> bool:
    """Automation requires explicit allow-all or a non-empty domain allowlist."""
    if policy.allow_all_eligible_tabs:
        return True
    return bool(normalize_domain_patterns(policy.authorized_domains))


def is_tab_accessible(
    *,
    tab_id: int,
    url: str,
    domain: str,
    policy: ExtensionAccessPolicy,
    respect_pause: bool = True,
) -> bool:
    """Return True when a tab may be listed, relay-synced, or attached."""
    if respect_pause and tab_id in policy.paused_tab_ids:
        return False
    if is_internal_browser_url(url):
        return False
    if policy.allow_all_eligible_tabs:
        return is_eligible_http_url(url)
    patterns = normalize_domain_patterns(policy.authorized_domains)
    if not patterns:
        return False
    tab_domain = domain.strip().lower().rstrip(".")
    if not tab_domain and url:
        try:
            tab_domain = (urlparse(url).hostname or "").strip().lower().rstrip(".")
        except ValueError:
            tab_domain = ""
    return match_domain(tab_domain, patterns)


def is_navigation_target_allowed(
    target_url: str,
    policy: ExtensionAccessPolicy,
) -> bool:
    """Check whether a navigation target URL is permitted under *policy*."""
    if is_internal_browser_url(target_url):
        return False
    if policy.allow_all_eligible_tabs:
        return is_eligible_http_url(target_url)
    patterns = normalize_domain_patterns(policy.authorized_domains)
    if not patterns:
        return False
    try:
        host = (urlparse(target_url).hostname or "").strip().lower().rstrip(".")
    except ValueError:
        return False
    if not host:
        return False
    return match_domain(host, patterns)


def prune_paused_tab_ids(
    paused_tab_ids: frozenset[int],
    active_tab_ids: frozenset[int],
) -> frozenset[int]:
    """Drop pause entries for tab ids that no longer exist (Chrome reuses tab ids)."""
    if not paused_tab_ids:
        return paused_tab_ids
    return frozenset(tab_id for tab_id in paused_tab_ids if tab_id in active_tab_ids)
