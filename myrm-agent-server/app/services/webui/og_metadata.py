"""Open Graph metadata fetcher with in-memory LRU cache.

[INPUT]
HTTP(S) page URLs from WebUI embed link preview requests.

[OUTPUT]
Parsed Open Graph title/description/image fields for JSON API responses.

[POS]
WebUI service helper. Server-side OG fetch to bypass browser CORS for embed previews.

Proxies OG metadata requests through the server to solve CORS issues
for the WebUI embed system, enabling rich link previews across all
deployment modes (local/tauri/cloud).
"""

from __future__ import annotations

import html
import logging
import re
from collections import OrderedDict
from typing import TypedDict

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
_MAX_BODY_BYTES = 64 * 1024
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
    """Fetch Open Graph metadata for a URL with caching."""
    try:
        parsed = httpx.URL(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return {"url": url}
    except Exception:
        return {"url": url}

    if (cached := _cache_get(url)) is not None:
        return cached

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return _cache_put(url, {"url": url})

            body = resp.text[:_MAX_BODY_BYTES]
            return _cache_put(url, _parse_og_tags(body, url))
    except Exception:
        logger.debug("Failed to fetch OG metadata for %s", url, exc_info=True)
        return _cache_put(url, {"url": url})
