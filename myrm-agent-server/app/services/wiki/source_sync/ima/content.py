"""Resolve one ima item into wiki-ready Markdown plus an honest list of what was lost.

[INPUT]
- .client::ImaClient / .media::download_media (POS: ima reads)
- app.services.wiki.source_sync.content_convert::bytes_to_wiki_markdown (POS: pdf/docx/office/text conversion)
- myrm_agent_harness web_fetch_tools.crawl + wiki ingress asset localization (POS: web pages, WeChat articles, images)

[OUTPUT]
- ImaContent / ImaUnsupported / ImaDuplicate: the three outcomes of resolving an item
- resolve_kb_item / resolve_note / render_document

[POS]
Reuses the existing conversion and web-fetch stacks instead of re-implementing them. Lossy outcomes are named
(``images_remote``, ``body_truncated``, ``layout_flattened``) so the ledger can report fidelity instead of claiming
every import is exact. A note's plain text is all ima's API offers, so it is the baseline, not a loss: counting it
would flag every note as simplified and bury the items that really lost something.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.web_fetch import web_fetch_tools
from myrm_agent_harness.toolkits.web_fetch.extractors import WEIXIN_BODY_TRUNCATED_MARKER
from myrm_agent_harness.toolkits.wiki.pipeline.ingress.asset_store import localize_public_markdown_images

from app.services.wiki.source_sync.content_convert import bytes_to_wiki_markdown
from app.services.wiki.source_sync.publish_helpers import build_frontmatter

from .client import ImaClient
from .errors import ImaPageUnavailableError
from .ledger import LedgerRow
from .media import download_media
from .models import MEDIA_FILE_EXTENSIONS, MEDIA_HTML, MEDIA_LABELS, MEDIA_NOTE, MEDIA_WEB_TYPES

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki import WikiStructure

WEB_FETCH_TIMEOUT_S = 90.0

# PDF and slide decks are reduced to their text; layout, shapes and embedded pictures are not carried over.
_LAYOUT_FLATTENED_TYPES = frozenset({1, 4})
_REMOTE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*<?https?://", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ImaContent:
    body: str
    lossy: tuple[str, ...] = ()
    source_url: str = ""
    type_label: str = ""


@dataclass(frozen=True, slots=True)
class ImaUnsupported:
    reason: str


@dataclass(frozen=True, slots=True)
class ImaDuplicate:
    """The item is a note that the notes lane already imports."""


type ResolvedItem = ImaContent | ImaUnsupported | ImaDuplicate


def _filename(title: str, extension: str) -> str:
    return title if PurePosixPath(title).suffix.lower() == extension else f"{title}{extension}"


async def _html_to_markdown(html: str, *, base_url: str) -> str:
    from myrm_agent_harness.toolkits.web_fetch.processing.content_pruning import ContentPruningFilter
    from myrm_agent_harness.toolkits.web_fetch.processing.markdown_generator import MarkdownGenerator

    def convert() -> str:
        generator = MarkdownGenerator(content_filter=ContentPruningFilter())
        return (generator.generate_markdown(html, base_url=base_url, citations=False).raw_markdown or "").strip()

    return await asyncio.to_thread(convert)


async def _localize_images(structure: WikiStructure, body: str, *, base_url: str, raw_relative: str) -> tuple[str, list[str]]:
    localized, _ = await localize_public_markdown_images(structure, body, base_url=base_url, raw_relative=raw_relative)
    return localized, (["images_remote"] if _REMOTE_IMAGE_RE.search(localized) else [])


async def _web_content(url: str, *, type_label: str, structure: WikiStructure, raw_relative: str) -> ImaContent:
    try:
        document = await asyncio.wait_for(web_fetch_tools.crawl(url, allow_escalation=False), timeout=WEB_FETCH_TIMEOUT_S)
    except TimeoutError as exc:
        raise ImaPageUnavailableError("web page fetch timed out") from exc
    if document is None or not document.page_content.strip():
        raise ImaPageUnavailableError("web page could not be fetched")
    body, lossy = await _localize_images(structure, document.page_content, base_url=url, raw_relative=raw_relative)
    if WEIXIN_BODY_TRUNCATED_MARKER in body:
        lossy.append("body_truncated")
    return ImaContent(body=body, lossy=tuple(lossy), source_url=url, type_label=type_label)


async def resolve_kb_item(
    client: ImaClient,
    row: LedgerRow,
    *,
    structure: WikiStructure,
    raw_relative: str,
    note_covered: Callable[[str], Awaitable[bool]],
) -> ResolvedItem:
    info = await client.get_media_info(row.remote_id)
    media_type = info.media_type if info.media_type is not None else row.media_type
    if media_type is None:
        return ImaUnsupported("unsupported_type")
    label = MEDIA_LABELS.get(media_type, "unknown")

    if media_type == MEDIA_NOTE:
        if not info.note_id:
            return ImaUnsupported("no_download_url")
        if await note_covered(info.note_id):
            return ImaDuplicate()
        return await _note_text(client, info.note_id)

    if media_type in MEDIA_WEB_TYPES and info.url and not info.headers:
        return await _web_content(info.url, type_label=label, structure=structure, raw_relative=raw_relative)

    is_html = media_type == MEDIA_HTML or media_type in MEDIA_WEB_TYPES
    extension = ".html" if is_html else MEDIA_FILE_EXTENSIONS.get(media_type)
    if extension is None:
        return ImaUnsupported("unsupported_type")
    if not info.url:
        return ImaUnsupported("no_download_url")

    data = await download_media(info.url, info.headers)
    if is_html:
        body = await _html_to_markdown(data.decode("utf-8", errors="replace"), base_url=info.url)
        if not body:
            return ImaUnsupported("no_text")
        body, lossy = await _localize_images(structure, body, base_url=info.url, raw_relative=raw_relative)
        return ImaContent(body=body, lossy=tuple(lossy), type_label=label)

    markdown = await bytes_to_wiki_markdown(
        data,
        filename=_filename(row.title, extension),
        mime_type="",
        structure=structure,
        raw_relative=raw_relative,
    )
    if not markdown:
        return ImaUnsupported("no_text")
    layout_notes = ("layout_flattened",) if media_type in _LAYOUT_FLATTENED_TYPES else ()
    return ImaContent(body=markdown, lossy=layout_notes, type_label=label)


async def _note_text(client: ImaClient, note_id: str) -> ImaContent | ImaUnsupported:
    text = await client.get_note_text(note_id)
    if not text:
        return ImaUnsupported("no_text")
    return ImaContent(body=text, type_label="note")


async def resolve_note(client: ImaClient, note_id: str) -> ImaContent | ImaUnsupported:
    return await _note_text(client, note_id)


def _one_line(text: str) -> str:
    """Titles and folder names are remote text: a line break inside a frontmatter value would end or forge fields."""
    return " ".join(text.split())


def render_document(*, row: LedgerRow, content: ImaContent, modified: str = "") -> str:
    """Deterministic raw file text: identical input always yields identical bytes, so re-syncs skip cleanly."""
    title = _one_line(row.title)
    extra = {
        "ima_container": _one_line(row.container_name),
        "ima_folder": _one_line(row.folder_path),
        "ima_type": content.type_label,
    }
    extra["fidelity"] = "partial" if content.lossy else "full"
    if content.lossy:
        extra["fidelity_notes"] = ",".join(content.lossy)
    if content.source_url:
        extra["source_url"] = _one_line(content.source_url)
    if modified:
        extra["modified"] = modified
    frontmatter = build_frontmatter(
        source="ima",
        title=title,
        external_id=row.item_key,
        extra={key: value for key, value in extra.items() if value},
    )
    body = content.body.strip()
    heading = "" if body.startswith("# ") else f"# {title}\n\n"
    return f"{frontmatter}{heading}{body}\n"
