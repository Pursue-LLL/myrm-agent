"""Document body for a Feishu comment turn.

A comment turn carries the comment thread and the quoted passage, and the agent has no tool that opens the document it
was asked about. This module reads the body so the turn can answer questions about the whole document.

[INPUT]
- providers.feishu.api::FeishuClient (POS: Feishu OpenAPI client; ``get_document_content`` returns a docx as Markdown)
- providers.feishu.comment_handler::CommentRouteInfo (POS: parsed comment routing info)
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
    from app.channels.providers.feishu.comment_handler import CommentRouteInfo

logger = logging.getLogger(__name__)

# Only new-style documents have a Markdown export.
_READABLE_FILE_TYPE = "docx"
# The comment reply waits for this read, so a slow document must not hold it up for long.
_READ_TIMEOUT_SECONDS = 15.0
# 2889902: the app may not read this document. 99991672: the app lacks the ``docs:document.content:read`` scope.
_DENIED_CODES = frozenset({2889902, 99991672})
_HTTP_FORBIDDEN = 403
# 2889925: the document is beyond the export size limit.
_TOO_LARGE_CODES = frozenset({2889925})


def _status_for(code: int) -> ContextDocumentStatus:
    if code in _DENIED_CODES or code == _HTTP_FORBIDDEN:
        return ContextDocumentStatus.DENIED
    if code in _TOO_LARGE_CODES:
        return ContextDocumentStatus.TOO_LARGE
    return ContextDocumentStatus.UNAVAILABLE


async def read_comment_document(client: FeishuClient, route: CommentRouteInfo) -> ContextDocument:
    """The commented document's body as Markdown, or the reason there is none. Never raises."""
    if route.file_type != _READABLE_FILE_TYPE:
        logger.info("Feishu comment document not read: file_type=%s has no Markdown export", route.file_type)
        return ContextDocument(ContextDocumentStatus.UNSUPPORTED)

    started = time.monotonic()
    try:
        async with asyncio.timeout(_READ_TIMEOUT_SECONDS):
            content = await client.get_document_content(route.file_token, route.file_type)
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
