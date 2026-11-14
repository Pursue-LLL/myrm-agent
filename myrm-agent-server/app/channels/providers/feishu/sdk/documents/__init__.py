"""Feishu document-level API methods for FeishuClient, composed from per-domain mixins.

[INPUT]
- ._drive::FeishuDriveMixin (POS: Drive meta, wiki lookup, media, folder listing)
- ._comments::FeishuCommentsMixin (POS: comment threads)
- ._docx::DocumentContent, FeishuDocxMixin (POS: Docx content and blocks)
- ._bitable::FeishuBitableMixin (POS: Bitable records and Bases)

[OUTPUT]
- FeishuDocumentsMixin: every document-level API method, as one mixin for FeishuClient.
- DocumentContent: result type of ``get_document_content``.

[POS]
Facade of the document domain; FeishuClient inherits this one class.
"""

from __future__ import annotations

from ._bitable import FeishuBitableMixin
from ._comments import FeishuCommentsMixin
from ._docx import DocumentContent, FeishuDocxMixin
from ._drive import FeishuDriveMixin


class FeishuDocumentsMixin(FeishuDriveMixin, FeishuCommentsMixin, FeishuDocxMixin, FeishuBitableMixin):
    """Drive, wiki, comment, Docx and Bitable operations."""


__all__ = ["DocumentContent", "FeishuDocumentsMixin"]
