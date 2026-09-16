"""Feishu domain subpackage: connector + pure renderers.

[POS]
Feishu ingest domain for wiki source_sync, mirroring the gmail/ subpackage
layout: feishu.py is the connector facade, feishu_render*.py are pure
block/inline → Markdown renderers with no I/O.
"""

from app.services.wiki.source_sync.feishu.feishu import (
    _localize_feishu_images,
    feishu_docx_blocks_to_markdown,
    is_feishu_wiki_sync_available,
    sync_feishu_docs_to_wiki,
)

__all__ = [
    "_localize_feishu_images",
    "feishu_docx_blocks_to_markdown",
    "is_feishu_wiki_sync_available",
    "sync_feishu_docs_to_wiki",
]