"""Document body for a Feishu comment turn.

A comment turn carries the comment thread and the quoted passage, and the agent has no tool that opens the document it
was asked about. This module reads the body so the turn can answer questions about the whole document.

[INPUT]
- providers.feishu.api::FeishuClient (POS: Feishu OpenAPI client; a docx as Markdown, or as plain text without the Markdown scope)
- providers.feishu.comment.handler::CommentRouteInfo (POS: parsed comment routing info)
- channels.types::ContextDocument, ContextDocumentStatus (POS: reference document contract)

[OUTPUT]
- read_comment_document(): the commented document's body, or the reason there is none (never raises)

[POS]
Provider-side producer of the reference document behind ``FeishuInboundMixin.read_context_document``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.channels.types import ContextDocument, ContextDocumentStatus

if TYPE_CHECKING:
    from app.channels.providers.feishu.api import FeishuClient
    from app.channels.providers.feishu.comment.handler import CommentRouteInfo
    from app.channels.providers.feishu.sdk import DocumentContent

logger = logging.getLogger(__name__)

# Only new-style documents have a Markdown export.
_READABLE_FILE_TYPE = "docx"
# The comment reply waits for this read, so a slow document must not hold it up for long.
_READ_TIMEOUT_SECONDS = 15.0
# 99991672: the app lacks the scope of the API it called, so no document is readable until an administrator grants it.
_SCOPE_MISSING_CODES = frozenset({99991672})
# 2889902 (Markdown export) and 1770032 (plain text): the app was not added to this document.
_DENIED_CODES = frozenset({2889902, 1770032})
_HTTP_FORBIDDEN = 403
# 2889925 (Markdown export) and 1770033 (plain text): the document is beyond the size limit.
_TOO_LARGE_CODES = frozenset({2889925, 1770033})


def _status_for(code: int) -> ContextDocumentStatus:
    if code in _SCOPE_MISSING_CODES:
        return ContextDocumentStatus.SCOPE_MISSING
    if code in _DENIED_CODES or code == _HTTP_FORBIDDEN:
        return ContextDocumentStatus.DENIED
    if code in _TOO_LARGE_CODES:
        return ContextDocumentStatus.TOO_LARGE
    return ContextDocumentStatus.UNAVAILABLE


async def _fetch(client: FeishuClient, route: CommentRouteInfo) -> DocumentContent:
    """The Markdown export, or the plain text when the app has not been granted the export's scope."""
    content = await client.get_document_content(route.file_token, route.file_type)
    if content.code not in _SCOPE_MISSING_CODES:
        return content
    logger.warning(
        "Feishu app lacks scope docs:document.content:read; reading document %s as plain text "
        "(docx:document:readonly). An administrator can grant the scope to get Markdown.",
        route.file_token,
    )
    return await client.get_document_plain_text(route.file_token)


async def read_comment_document(client: FeishuClient, route: CommentRouteInfo) -> ContextDocument:
    """The commented document's body (Markdown, plain text when only that is readable), or the reason there is none.

    Never raises.
    """
    if route.file_type != _READABLE_FILE_TYPE:
        logger.info("Feishu comment document not read: file_type=%s has no Markdown export", route.file_type)
        return ContextDocument(ContextDocumentStatus.UNSUPPORTED)

    started = time.monotonic()
    try:
        async with asyncio.timeout(_READ_TIMEOUT_SECONDS):
            content = await _fetch(client, route)
    except Exception:
        # The comment reply must go out whether or not the body could be read.
        logger.warning("Feishu comment document read failed: file=%s", route.file_token, exc_info=True)
        return ContextDocument(ContextDocumentStatus.UNAVAILABLE)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if content.ok:
        logger.info(
            "Feishu comment document read: file=%s chars=%d elapsed_ms=%d",
            route.file_token,
            len(content.markdown),
            elapsed_ms,
        )
        return ContextDocument.ready(content.markdown)

    status = _status_for(content.code)
    level = logging.INFO if status is ContextDocumentStatus.TOO_LARGE else logging.WARNING
    logger.log(
        level,
        "Feishu comment document unreadable: file=%s status=%s code=%d message=%s elapsed_ms=%d",
        route.file_token,
        status.value,
        content.code,
        content.message,
        elapsed_ms,
    )
    return ContextDocument(status)
