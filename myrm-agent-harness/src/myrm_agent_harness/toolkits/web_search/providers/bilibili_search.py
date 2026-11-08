"""Bilibili search fast-path.

Direct search via Bilibili's public API, bypassing generic search engines.
Used when every query is scoped to Bilibili videos by its ``site:`` operators (``is_bilibili_video_query``), e.g.
``site:bilibili.com Rust 入门``, and no ``time_range`` is set (the request carries no date parameter, so a time
window goes to the provider search).

Returns structured results with play count, author, duration — data that
generic engines (Google, SearxNG) cannot provide for Bilibili content.

Scope limitation: Bilibili (direct API) is the only platform-specific search
fast-path in the toolkit. Additional platforms must use Skill/MCP — not toolkit
built-ins.

[INPUT]
- web_search.core.common::SearchResult (POS: Unified search result dataclass)
- web_search.processing._explicit_params::split_site_operators (POS: Explicit constraint mapper; the one reading of a query's site: operators)

[OUTPUT]
- is_bilibili_video_query: Whether a query is scoped to Bilibili videos: its site: operators name bilibili.com or its /video section and no other domain
- search_bilibili: Async Bilibili keyword search (site: operators are removed from the keyword) returning SearchResult list or None

[POS]
Bilibili search fast-path. Returns structured SearchResult list via public API;
returns None when the API fails or has no video to link, so the caller falls back to the provider search.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import TypedDict

from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.processing._explicit_params import split_site_operators

logger = logging.getLogger(__name__)

_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/all/v2"
_REQUEST_TIMEOUT = 8
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")


class _VideoEntry(TypedDict, total=False):
    """The fields of a Bilibili video search hit that this module reads."""

    title: str
    author: str | None
    play: int | None
    duration: str | None
    bvid: str
    description: str | None


_BILIBILI_HOST = "bilibili.com"
# The API returns videos only, so only the whole site and its video section ask for what it can return.
_VIDEO_SECTIONS = ("", "video")


def _scopes_to_videos(domain: str) -> bool:
    """Whether a ``site:`` domain is bilibili.com itself or a path in its ``/video`` section."""
    host, _, path = domain.lower().partition("/")
    return host == _BILIBILI_HOST and path.partition("/")[0] in _VIDEO_SECTIONS


def is_bilibili_video_query(query: str) -> bool:
    """Whether the ``site:`` operators of ``query`` scope it to Bilibili videos.

    Every included domain must be bilibili.com or its ``/video`` section; excluded domains do not matter.
    ``-site:bilibili.com`` excludes the site, a second domain widens the search beyond it, and the other sections
    (``/read``, ``/opus``) hold what the video API cannot return: none of them asks for Bilibili videos.
    """
    included = split_site_operators(query).included
    return bool(included) and all(_scopes_to_videos(domain) for domain in included)


def _strip_html(text: str) -> str:
    """Remove HTML tags (e.g., <em class="keyword">) from API response text."""
    return _HTML_TAG_RE.sub("", text)


def _format_play_count(count: int) -> str:
    if count >= 10000:
        return f"{count / 10000:.1f}万"
    return str(count)


async def search_bilibili(
    keyword: str,
    max_results: int = 10,
) -> list[SearchResult] | None:
    """Search Bilibili for videos matching keyword.

    Args:
        keyword: Search query string. The API takes plain keywords, so its ``site:`` operators are removed first.
        max_results: Maximum number of results to return (capped at 20, min 1)

    Returns:
        List of SearchResult, or None when nothing can be answered: the request failed, the API returned no video
        that can be linked, or no keyword is left once the ``site:`` operators are removed (no request is made
        then). The caller falls back to the provider search.
    """
    keyword = split_site_operators(keyword).remainder
    if not keyword:
        return None
    max_results = max(1, min(max_results, 20))

    def _do_search() -> list[SearchResult] | None:
        try:
            params = urllib.parse.urlencode({"keyword": keyword, "page": 1})
            url = f"{_SEARCH_API}?{params}"
            req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)  # noqa: S310
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("code") != 0:
                logger.info("Bilibili search API returned code %s", data.get("code"))
                return None

            result_groups = (data.get("data") or {}).get("result", [])
            videos: list[_VideoEntry] = []
            for group in result_groups:
                if group.get("result_type") == "video":
                    videos = group.get("data", [])
                    break

            # The video group also lists live rooms, which come without a bvid: there is no video to link to.
            linkable = [(bvid, v) for v in videos if (bvid := v.get("bvid"))]
            if not linkable:
                logger.info("Bilibili search returned 0 video results for: %s", keyword[:50])
                return None

            results: list[SearchResult] = []
            for bvid, v in linkable[:max_results]:
                # Tags go first so that markup the API escaped stays text.
                title = html.unescape(_strip_html(v.get("title", "")))
                author = v.get("author", "")
                play = v.get("play", 0)
                duration = v.get("duration", "")
                # A video may come without a description (null): it is still a result.
                description = html.unescape(v.get("description") or "")

                link = f"https://www.bilibili.com/video/{bvid}"
                snippet_parts = []
                if author:
                    snippet_parts.append(f"UP主: {author}")
                if play:
                    snippet_parts.append(f"播放: {_format_play_count(play)}")
                if duration:
                    snippet_parts.append(f"时长: {duration}")
                if description and description != "-":
                    snippet_parts.append(description[:100])

                results.append(
                    SearchResult(
                        title=title,
                        link=link,
                        snippet=" | ".join(snippet_parts) if snippet_parts else title,
                    )
                )

            logger.info("Bilibili search success: keyword=%s results=%d", keyword[:30], len(results))
            return results

        except Exception as exc:
            logger.warning("Bilibili search failed for '%s': %s", keyword[:30], exc)
            return None

    return await asyncio.to_thread(_do_search)
