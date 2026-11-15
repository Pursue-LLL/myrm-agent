"""URL normalization for a higher cache hit rate.

Strips known tracking parameters (``utm_*``, ``fbclid``, ``gclid``, ``_hsenc``, ``li_fat_id``, ``ttclid``
and others), lowercases the scheme and host, drops default ports, collapses repeated slashes in the path,
sorts the query parameters and drops a plain anchor, so URLs that differ only in those details share one
cache key.

The parameters come from Google Analytics, Facebook, Google Ads, Bing, Mailchimp, HubSpot, Adobe, LinkedIn,
Twitter and TikTok. Generic names such as ``ref`` and ``source`` stay in the key because sites use them to
select content (GitHub's contents API picks the branch or tag with ``?ref=``), and so does a hash route
(``#/inbox``, ``#!/inbox``) because a single-page app shows a different view for each one.

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
    }
)

# A fragment starting with one of these is a client-side route, not an anchor.
_ROUTE_FRAGMENT_PREFIXES = ("/", "!/")


def _route_fragment(fragment: str) -> str:
    """Return ``fragment`` when it is a hash route, an empty string for a plain anchor.

    A hash-routed page shows a different view for ``#/inbox`` and ``#/sent`` while the server sees one URL, so
    the route belongs in the key; an anchor such as ``#section`` only scrolls inside the same page.
    """
    return fragment if fragment.startswith(_ROUTE_FRAGMENT_PREFIXES) else ""


def normalize_url(url: str) -> str:
    """Normalize a URL so that equivalent URLs map to the same cache key.

    Steps:
    1. Drop tracking parameters (``utm_*``, ``fbclid``, ...).
    2. Lowercase the scheme.
    3. Lowercase the host.
    4. Drop the default port (``:80`` for http, ``:443`` for https).
    5. Collapse repeated slashes in the path.
    6. Sort the query parameters alphabetically.
    7. Drop the fragment unless it is a hash route (``#/...`` or ``#!/...``).

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

    return urlunparse((scheme, netloc, path, parsed.params, sorted_query, _route_fragment(parsed.fragment)))
