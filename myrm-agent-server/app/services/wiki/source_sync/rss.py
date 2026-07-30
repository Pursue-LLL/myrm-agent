"""RSS/Atom feed → wiki raw sync."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.services.wiki.source_sync.publish_helpers import build_frontmatter, publish_source_markdown, sanitize_path_segment
from app.services.wiki.source_sync.schemas import WikiSourceSyncResult
from myrm_agent_harness.toolkits.wiki import WikiStructure

logger = logging.getLogger(__name__)

_STRIP_TAGS = re.compile(r"<[^>]+>")


async def sync_rss_feeds_to_wiki(
    structure: WikiStructure,
    *,
    feed_urls: list[str],
    max_items: int,
    auto_compile: bool,
    compiler_enqueue: object | None,
) -> WikiSourceSyncResult:
    result = WikiSourceSyncResult(source="rss")
    per_feed = max(1, max_items // max(len(feed_urls), 1))
    month = datetime.now(UTC).strftime("%Y-%m")

    for feed_url in feed_urls:
        url = feed_url.strip()
        if not url:
            continue
        if not _is_allowed_feed_url(url):
            result.failed += 1
            result.errors.append(f"invalid feed url: {url}")
            continue
        try:
            entries = await _fetch_feed_entries(url, limit=per_feed)
        except Exception as exc:
            logger.warning("RSS fetch failed for %s: %s", url, exc)
            result.failed += 1
            result.errors.append(f"{url}: {exc}")
            continue

        feed_slug = sanitize_path_segment(urlparse(url).netloc or "feed")
        for entry in entries:
            try:
                relative_path = f"rss/{feed_slug}/{month}/{entry.slug}.md"
                frontmatter = build_frontmatter(
                    source="rss",
                    title=entry.title,
                    external_id=entry.external_id,
                    extra={"feed": url, "link": entry.link},
                )
                content = frontmatter + f"# {entry.title}\n\n{entry.body}\n"
                if entry.link:
                    content += f"\n[Source]({entry.link})\n"
                publish = await publish_source_markdown(
                    structure,
                    relative_path=relative_path,
                    content=content,
                    auto_compile=auto_compile,
                    compiler_enqueue=compiler_enqueue,
                )
                if publish.written:
                    result.published += 1
                elif publish.conflict_skipped or publish.skipped:
                    result.skipped += 1
                else:
                    result.skipped += 1
            except Exception as exc:
                logger.warning("RSS publish failed: %s", exc)
                result.failed += 1
                result.errors.append(str(exc))

    return result


def _is_allowed_feed_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class _FeedEntry:
    __slots__ = ("title", "body", "link", "external_id", "slug")

    def __init__(self, *, title: str, body: str, link: str, external_id: str, slug: str) -> None:
        self.title = title
        self.body = body
        self.link = link
        self.external_id = external_id
        self.slug = slug


async def _fetch_feed_entries(url: str, *, limit: int) -> list[_FeedEntry]:
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "MyrmWikiSourceSync/1.0"})
        resp.raise_for_status()
        text = resp.text

    root = ET.fromstring(text)
    entries: list[_FeedEntry] = []

    for item in root.iter():
        tag = item.tag.split("}")[-1].lower()
        if tag not in {"item", "entry"}:
            continue
        title = _child_text(item, "title") or "(untitled)"
        link = _entry_link(item)
        body = _child_text(item, "description") or _child_text(item, "summary") or _child_text(item, "content")
        body = _strip_html(body)
        guid = _child_text(item, "guid") or _child_text(item, "id") or link or title
        slug = sanitize_path_segment(guid)[-80:]
        entries.append(
            _FeedEntry(
                title=title,
                body=body,
                link=link,
                external_id=guid,
                slug=slug,
            )
        )
        if len(entries) >= limit:
            break
    return entries


def _child_text(node: ET.Element, local_name: str) -> str:
    for child in node:
        if child.tag.split("}")[-1].lower() == local_name.lower():
            return (child.text or "").strip()
    return ""


def _entry_link(node: ET.Element) -> str:
    for child in node:
        local = child.tag.split("}")[-1].lower()
        if local == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
    return ""


def _strip_html(value: str) -> str:
    if not value:
        return ""
    return _STRIP_TAGS.sub(" ", value).strip()
