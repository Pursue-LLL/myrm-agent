"""Zotero library → wiki raw sync.

[INPUT]
- app.services.wiki.source_sync.publish_helpers (POS: publish_raw wrapper)

[OUTPUT]
- sync_zotero_library_to_wiki: pull Zotero top-level items into wiki raw/

[POS]
Deterministic Zotero Web API v3 ingest path for wiki source sync; zero LLM.
Fetches top-level items (publication metadata) newest-modified first, renders
them as literature notes with citation frontmatter, and pulls user annotations
(highlights / annotation notes) from child items on a best-effort basis.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.source_sync.publish_helpers import (
    build_frontmatter,
    publish_source_markdown,
    sanitize_path_segment,
)
from app.services.wiki.source_sync.schemas import WikiSourceSyncResult

logger = logging.getLogger(__name__)

_ZOTERO_TIMEOUT = 25.0
_MAX_PER_REQUEST = 50  # Zotero API page-size cap


async def sync_zotero_library_to_wiki(
    structure: WikiStructure,
    *,
    api_key: str,
    user_id: str,
    max_items: int,
    auto_compile: bool,
    compiler_enqueue: object | None,
    base_url: str = "https://api.zotero.org",
) -> WikiSourceSyncResult:
    """Sync a Zotero user library into wiki raw/ as literature notes.

    Deterministic pull: most-recently-modified top-level items first, capped by
    ``max_items`` per run. Zero-LLM: rendering is template-based and publication
    goes through the shared raw gate.
    """
    result = WikiSourceSyncResult(source="zotero")
    if not api_key or not user_id:
        result.failed += 1
        result.errors.append("zotero api_key/user_id not configured")
        return result
    if not _is_allowed_base_url(base_url):
        result.failed += 1
        result.errors.append(f"invalid zotero base url: {base_url}")
        return result

    month = datetime.now(UTC).strftime("%Y-%m")
    try:
        items = await _fetch_top_level_items(
            base_url=base_url,
            api_key=api_key,
            user_id=user_id,
            limit=max_items,
        )
    except Exception as exc:
        logger.warning("Zotero fetch failed: %s", exc)
        result.failed += 1
        result.errors.append(str(exc))
        return result

    for item in items:
        item_key = str(item.get("key") or "")
        try:
            published = await _render_and_publish_item(
                structure,
                item=item,
                month=month,
                base_url=base_url,
                api_key=api_key,
                user_id=user_id,
                auto_compile=auto_compile,
                compiler_enqueue=compiler_enqueue,
            )
            if published:
                result.published += 1
            else:
                result.skipped += 1
        except Exception as exc:
            logger.warning("Zotero publish failed for item %s: %s", item_key, exc)
            result.failed += 1
            result.errors.append(f"item {item_key}: {exc}")
    return result


async def _fetch_top_level_items(
    *,
    base_url: str,
    api_key: str,
    user_id: str,
    limit: int,
) -> list[dict[str, object]]:
    """Fetch most-recently-modified top-level items from the user library."""
    headers = {"Zotero-API-Key": api_key, "Zotero-API-Version": "3"}
    url = f"{base_url.rstrip('/')}/users/{user_id}/items/top"
    async with httpx.AsyncClient(timeout=_ZOTERO_TIMEOUT) as client:
        response = await client.get(
            url,
            params={
                "format": "json",
                "limit": min(max(limit, 1), _MAX_PER_REQUEST),
                "sort": "dateModified",
                "direction": "desc",
            },
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, list):
        raise ValueError("unexpected Zotero API response shape")
    return [entry for entry in data if isinstance(entry, dict)]


async def _render_and_publish_item(
    structure: WikiStructure,
    *,
    item: dict[str, object],
    month: str,
    base_url: str,
    api_key: str,
    user_id: str,
    auto_compile: bool,
    compiler_enqueue: object | None,
) -> bool:
    """Render one Zotero item into a literature note; returns True when written."""
    data = item.get("data")
    if not isinstance(data, dict):
        return False

    key = str(item.get("key") or data.get("key") or "")
    if not key:
        return False

    item_type = str(data.get("itemType") or "attachment")
    # Attachments are children rather than literature notes; skip silently.
    if item_type == "attachment":
        return False

    title = str(data.get("title") or data.get("name") or "(untitled)")
    abstract_raw = data.get("abstractNote")
    abstract = abstract_raw if isinstance(abstract_raw, str) else ""

    creators = data.get("creators")
    authors = _format_creators(creators if isinstance(creators, list) else [])

    doi = str(data.get("DOI") or "")
    url = str(data.get("url") or "")
    year = str(data.get("date") or "")

    annotations = await _fetch_annotations(
        base_url=base_url,
        api_key=api_key,
        user_id=user_id,
        item_key=key,
    )

    external_id = f"zotero:{key}"
    relative_path = f"zotero/{month}/{sanitize_path_segment(key)}.md"
    frontmatter = build_frontmatter(
        source="zotero",
        title=title,
        external_id=external_id,
        extra={
            "zotero_key": key,
            "item_type": item_type,
            "authors": ", ".join(authors),
            "doi": doi,
            "year": year,
            "url": url,
        },
    )
    content = _render_note(
        title=title,
        item_type=item_type,
        authors=authors,
        doi=doi,
        url=url,
        year=year,
        abstract=abstract,
        annotation_lines=annotations,
    )
    publish = await publish_source_markdown(
        structure,
        relative_path=relative_path,
        content=frontmatter + content,
        auto_compile=auto_compile,
        compiler_enqueue=compiler_enqueue,
    )
    return bool(publish.written)


def _format_creators(creators: list[object]) -> list[str]:
    names: list[str] = []
    for creator in creators:
        if not isinstance(creator, dict):
            continue
        first = str(creator.get("firstName") or "")
        last = str(creator.get("lastName") or creator.get("name") or "")
        label = f"{first} {last}".strip() if first else last
        if label:
            names.append(label)
    return names


async def _fetch_annotations(
    *,
    base_url: str,
    api_key: str,
    user_id: str,
    item_key: str,
) -> list[str]:
    """Fetch highlight/note annotation lines for an item (best-effort, non-fatal)."""
    try:
        headers = {"Zotero-API-Key": api_key, "Zotero-API-Version": "3"}
        url = f"{base_url.rstrip('/')}/users/{user_id}/items/{item_key}/children"
        async with httpx.AsyncClient(timeout=_ZOTERO_TIMEOUT) as client:
            response = await client.get(
                url,
                params={"format": "json", "limit": _MAX_PER_REQUEST},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.debug("Zotero annotations fetch skipped for %s: %s", item_key, exc)
        return []
    if not isinstance(payload, list):
        return []
    return _render_annotations(payload)


def _render_annotations(children: list[object]) -> list[str]:
    lines: list[str] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        data = child.get("data")
        if not isinstance(data, dict):
            continue
        if str(data.get("itemType") or "") != "annotation":
            continue
        annotation_type = str(data.get("annotationType") or "")
        text = str(
            data.get("annotationText") or data.get("annotationComment") or ""
        ).strip()
        if not text:
            continue
        if annotation_type == "highlight":
            lines.append(f"> {text}\n> — highlight")
        else:
            lines.append(f"- {text}")
    return lines


def _render_note(
    *,
    title: str,
    item_type: str,
    authors: list[str],
    doi: str,
    url: str,
    year: str,
    abstract: str,
    annotation_lines: list[str],
) -> str:
    lines: list[str] = [f"# {title}", ""]
    meta_bits = [bit for bit in (", ".join(authors), year, item_type) if bit]
    if meta_bits:
        lines.append(f"**{meta_bits[0]}**")
        if len(meta_bits) > 1:
            lines[-1] = f"**{', '.join(meta_bits)}**"
    if doi:
        lines.append(f"DOI: `{doi}`")
    if url:
        lines.append(f"[Link]({url})")
    lines.append("")
    if abstract:
        lines.extend(["## Abstract", "", abstract, ""])
    if annotation_lines:
        lines.extend(["## Annotations", "", *annotation_lines, ""])
    return "\n".join(lines)


def _is_allowed_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
