"""Feishu document-comment turns: event handling, content extraction, reply routing and the commented document's body.

[INPUT]
- .handler::CommentHandler, CommentRouteInfo, COMMENT_DOC_PREFIX, NO_REPLY_SENTINEL, deliver_comment_reply, encode_comment_chat_id, parse_comment_recipient (POS: comment event to InboundMessage, reply routing and delivery)
- .document::read_comment_document (POS: body of the document a comment turn is about)

[OUTPUT]
- CommentHandler, CommentRouteInfo and the routing helpers: how a comment becomes a turn and where its reply goes.
- read_comment_document: the commented document's body for that turn.

[POS]
Facade of the comment domain; the Feishu inbound and outbound mixins import from here. ``content`` (pure extraction and
prompt building) is internal to ``handler``.
"""

from __future__ import annotations

from .document import read_comment_document
from .handler import (
    COMMENT_DOC_PREFIX,
    NO_REPLY_SENTINEL,
    CommentHandler,
    CommentRouteInfo,
    deliver_comment_reply,
    encode_comment_chat_id,
    parse_comment_recipient,
)

__all__ = [
    "COMMENT_DOC_PREFIX",
    "NO_REPLY_SENTINEL",
    "CommentHandler",
    "CommentRouteInfo",
    "deliver_comment_reply",
    "encode_comment_chat_id",
    "parse_comment_recipient",
    "read_comment_document",
]
