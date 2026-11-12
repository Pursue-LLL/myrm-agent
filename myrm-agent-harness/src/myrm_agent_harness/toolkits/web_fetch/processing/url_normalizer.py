"""URL normalization for a higher cache hit rate.

Strips known tracking parameters (``utm_*``, ``fbclid``, ``gclid``, ``_hsenc``, ``li_fat_id``, ``ttclid``
and others), lowercases the scheme and host, drops default ports, collapses repeated slashes in the path
and sorts the query parameters, so URLs that differ only in those details share one cache key.

The parameters come from Google Analytics, Facebook, Google Ads, Bing, Mailchimp, HubSpot, Adobe, LinkedIn,
Twitter and TikTok, plus the generic names ``ref``, ``referrer`` and ``source``.

[INPUT]
- (none)

[OUTPUT]
- normalize_url: canonical form of a URL, used as the cache key

[POS]
Pure URL canonicalizer. The fetch engine calls it once per request to build the key shared by its crawl
cache, failure cache, in-flight request map and access statistics.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = frozenset(
    {
        # Google Analytics
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "_ga",
        "_gid",
        "_gac",
        # Facebook
        "fbclid",
        "fb_action_ids",
        "fb_action_types",
        "fb_source",
        # Google Ads
        "gclid",
        "gclsrc",
        # Bing
        "msclkid",
        # Mailchimp
        "mc_cid",
        "mc_eid",
        # HubSpot
        "_hsenc",
        "_hsmi",
        # Adobe
        "s_cid",
        # LinkedIn
        "li_fat_id",
        "li_source",
        # Twitter
        "twclid",
        # TikTok
        "ttclid",
        # Generic
        "ref",
        "referrer",
        "source",
    }
)


def normalize_url(url: str) -> str:
    """Normalize a URL so that equivalent URLs map to the same cache key.

    Steps:
    1. Drop tracking parameters (``utm_*``, ``fbclid``, ...).
    2. Lowercase the scheme.
    3. Lowercase the host.
    4. Drop the default port (``:80`` for http, ``:443`` for https).
    5. Collapse repeated slashes in the path.
    6. Sort the query parameters alphabetically.
    7. Drop the fragment.

    Args:
        url: Original URL.

    Returns:
        The normalized URL.
    """
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    if (scheme == "http" and netloc.endswith(":80")) or (scheme == "https" and netloc.endswith(":443")):
        netloc = netloc.rsplit(":", 1)[0]

    path = parsed.path
    if path and "//" in path:
        path = "/".join(segment for segment in path.split("/") if segment)
        if not path.startswith("/"):
            path = "/" + path

    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered_params = {k: v for k, v in query_params.items() if k not in _TRACKING_PARAMS}
    sorted_query = urlencode(sorted(filtered_params.items()), doseq=True)

    return urlunparse((scheme, netloc, path, parsed.params, sorted_query, ""))
