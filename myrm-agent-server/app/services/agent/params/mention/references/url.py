"""[INPUT]
- myrm_agent_harness.toolkits.web_fetch.engine::FetchEngine (POS: layered crawl engine)
- ..context::MentionContext (POS: per-turn accumulation state)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- _fetch_url_content: SSRF-guarded URL fetch
- url_part: @url handler

[POS]
URL @ references. Fetch failures are reported as an explicit error fragment instead of a silent
drop, so the model knows the page was not read.
"""

from __future__ import annotations

import logging

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..xml import _MENTION_MAX_TOTAL_BYTES, _format_size, _xml_error, _xml_metadata, _xml_part

logger = logging.getLogger(__name__)

_URL_FETCH_TIMEOUT = 30


async def _fetch_url_content(url: str) -> str:
    """Fetch URL content using FetchEngine.

    Returns empty string on error or if URL is blocked by SSRF protection.
    """
    try:
        from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine

        engine = FetchEngine()
        doc = await engine.crawl(url)
        if doc and doc.page_content:
            return doc.page_content.strip()
    except Exception as e:
        logger.warning("Failed to fetch URL %s: %s", url, e)
    return ""


async def url_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    url = ref.url or ref.path or ""
    display_path = ref.label or f"@url:{url}"
    url_content = await _fetch_url_content(url)
    if url_content:
        url_bytes = len(url_content.encode("utf-8"))
        if ctx.total_bytes + url_bytes <= _MENTION_MAX_TOTAL_BYTES:
            ctx.parts.append(_xml_part(display_path, "url", url_content))
            ctx.total_bytes += url_bytes
        else:
            ctx.parts.append(
                _xml_metadata(
                    display_path,
                    "url",
                    f"Content too large ({_format_size(url_bytes)})",
                )
            )
    else:
        ctx.parts.append(_xml_error(display_path, "failed to fetch URL"))
