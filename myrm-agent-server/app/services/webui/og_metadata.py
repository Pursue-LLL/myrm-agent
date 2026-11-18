"""Open Graph metadata fetcher: SSRF-safe, bounded in bytes and time, with a bounded in-memory cache.

[INPUT]
- HTTP(S) page URLs from WebUI embed link preview requests
- myrm_agent_harness.core.security.http.secure_fetch::secure_get (POS: DNS-pinned GET with per-hop redirect validation and a streamed, size-capped body)
- myrm_agent_harness.utils.lru_cache::LRUCache (POS: LRU cache with TTL)
- app.core.brand::OFFICIAL_SITE_URL (POS: the official site, named in the crawler's User-Agent)

[OUTPUT]
- fetch_og_metadata: parsed Open Graph title/description/image fields for JSON API responses

[POS]
WebUI service helper. Server-side OG fetch to bypass browser CORS for embed previews in every deployment mode
(local/tauri/cloud).

The URL comes from whoever calls the endpoint and the page's title and description go back to that caller, so it is
fetched like every other user-supplied URL: public addresses only in every deployment mode (a host the operator lists
in ``MYRM_ALLOWED_INTERNAL_HOSTS`` is the one exception), each redirect hop checked and the connection made to the
address that was checked. The body is read as a stream and abandoned after 64 KiB, and the whole exchange has a
deadline, since a read timeout restarts with every byte. A URL that cannot be fetched, for any reason, yields
``{"url": url}``, so the endpoint does not tell a refused address from a dead one.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import TypedDict

import httpx
from myrm_agent_harness.core.security.http.secure_fetch import secure_get
from myrm_agent_harness.utils.lru_cache import LRUCache

from app.core.brand import OFFICIAL_SITE_URL

logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 64 * 1024
_REQUEST_TIMEOUT_SECONDS = 5.0
_DEADLINE_SECONDS = 10.0
_MAX_REDIRECTS = 3
_CACHE_MAX_ENTRIES = 256
_CACHE_TTL_SECONDS = 3600  # the lifetime the endpoint's ``Cache-Control`` gives the browser
_USER_AGENT = f"MyrmagentBot/1.0 (+{OFFICIAL_SITE_URL})"

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


_og_cache: LRUCache[OgMetadata] = LRUCache(maxsize=_CACHE_MAX_ENTRIES, ttl=_CACHE_TTL_SECONDS, id="og_metadata")


async def _fetch_og_metadata(url: str) -> OgMetadata:
    try:
        async with asyncio.timeout(_DEADLINE_SECONDS):
            resp = await secure_get(
                url,
                timeout=_REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": _USER_AGENT},
                max_redirects=_MAX_REDIRECTS,
                max_content_length=_MAX_BODY_BYTES,
                truncate=True,
            )
        resp.raise_for_status()
    except Exception:
        logger.debug("Failed to fetch OG metadata for %s", url, exc_info=True)
        return {"url": url}

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return {"url": url}
    return _parse_og_tags(resp.text, url)


async def fetch_og_metadata(url: str) -> OgMetadata:
    """Fetch Open Graph metadata for a URL; every outcome, a refused or failed fetch included, is cached for an hour."""
    cached = _og_cache.get(url)
    if cached is not None:
        return cached
    metadata = await _fetch_og_metadata(url)
    _og_cache.set(url, metadata)
    return metadata
