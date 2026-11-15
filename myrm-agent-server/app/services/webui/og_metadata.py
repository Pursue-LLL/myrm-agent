"""Open Graph metadata fetcher with in-memory LRU cache.

[INPUT]
- HTTP(S) page URLs from WebUI embed link preview requests
- myrm_agent_harness.core.security.http.secure_fetch::secure_get (POS: SSRF-protected download with per-hop DNS pinning, redirect validation and a size cap)

[OUTPUT]
Parsed Open Graph title/description/image fields for JSON API responses.

[POS]
WebUI service helper. Server-side OG fetch to bypass browser CORS for embed previews.

Proxies OG metadata requests through the server to solve CORS issues
for the WebUI embed system, enabling rich link previews across all
deployment modes (local/tauri/cloud). The URL is chosen by the caller, so
the page is downloaded through the SSRF shield: loopback, private and
cloud-metadata targets are refused on the first request and on every
redirect hop, and such a URL yields only ``{"url": url}``.
"""

from __future__ import annotations

import html
import logging
import re
from collections import OrderedDict
from typing import TypedDict

import httpx
from myrm_agent_harness.core.security.http.secure_fetch import secure_get

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0
# The tags read live in the first _PARSE_WINDOW_CHARS of the page, but secure_get aborts an oversized body instead of
# truncating it, so the download cap leaves room for heavy pages (inline state blobs) whose <head> is small.
_MAX_FETCH_BYTES = 4 * 1024 * 1024
_PARSE_WINDOW_CHARS = 64 * 1024
_USER_AGENT = "MyrmagentBot/1.0 (+https://myrmagent.com)"

_OG_RE = re.compile(
    r"<meta\s+(?:[^>]*?\s)?"
    r'(?:property|name)\s*=\s*["\']?(og:[^"\'>\s]+)["\']?\s+'
    r'content\s*=\s*["\']([^"\']*)["\']'
    r"|"
    r"<meta\s+(?:[^>]*?\s)?"
    r'content\s*=\s*["\']([^"\']*)["\']?\s+'
    r'(?:property|name)\s*=\s*["\']?(og:[^"\'>\s]+)["\']?',
    re.IGNORECASE,
)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

_FAVICON_RE = re.compile(
    r'<link\s+[^>]*?rel\s*=\s*["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*?href\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_ALLOWED_SCHEMES = {"http", "https"}


class OgMetadata(TypedDict, total=False):
    title: str
    description: str
    image: str
    site_name: str
    favicon: str
    url: str


def _parse_og_tags(body: str, source_url: str) -> OgMetadata:
    og: dict[str, str] = {}
    for m in _OG_RE.finditer(body):
        prop = m.group(1) or m.group(4)
        value = m.group(2) or m.group(3)
        if prop and value:
            og[prop.lower()] = html.unescape(value.strip())

    result: OgMetadata = {}
    if t := og.get("og:title"):
        result["title"] = t
    elif tm := _TITLE_RE.search(body):
        result["title"] = html.unescape(tm.group(1).strip())

    if d := og.get("og:description"):
        result["description"] = d
    if img := og.get("og:image"):
        result["image"] = img
    if sn := og.get("og:site_name"):
        result["site_name"] = sn

    if fm := _FAVICON_RE.search(body):
        href = fm.group(1)
        if href.startswith("//"):
            href = f"https:{href}"
        elif href.startswith("/"):
            try:
                parsed = httpx.URL(source_url)
                href = f"{parsed.scheme}://{parsed.host}{href}"
            except Exception:
                pass
        result["favicon"] = href

    result["url"] = source_url
    return result


_CACHE_MAX_ENTRIES = 256

# Least recently used first: every lookup and store moves its URL to the end, so trimming from the front
# discards the page previews have gone longest without asking for.
_og_cache: OrderedDict[str, OgMetadata] = OrderedDict()


def _cache_get(url: str) -> OgMetadata | None:
    cached = _og_cache.get(url)
    if cached is not None:
        _og_cache.move_to_end(url)
    return cached


def _cache_put(url: str, metadata: OgMetadata) -> OgMetadata:
    _og_cache[url] = metadata
    _og_cache.move_to_end(url)
    while len(_og_cache) > _CACHE_MAX_ENTRIES:
        _og_cache.popitem(last=False)
    return metadata


async def fetch_og_metadata(url: str) -> OgMetadata:
    """Fetch Open Graph metadata for a URL with caching.

    A URL the SSRF shield refuses, a page that fails to load and a non-HTML response all come back as
    ``{"url": url}`` and are cached like any other result.
    """
    try:
        parsed = httpx.URL(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return {"url": url}
    except Exception:
        return {"url": url}

    if (cached := _cache_get(url)) is not None:
        return cached

    try:
        resp = await secure_get(
            url,
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT},
            max_content_length=_MAX_FETCH_BYTES,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return _cache_put(url, {"url": url})

        return _cache_put(url, _parse_og_tags(resp.text[:_PARSE_WINDOW_CHARS], url))
    except Exception:
        logger.debug("Failed to fetch OG metadata for %s", url, exc_info=True)
        return _cache_put(url, {"url": url})
