"""Mem0 <-> Myrm memory format converter.

[INPUT]
app.schemas.memory.crud::MemoryItem (POS: Internal memory representation)
app.api.mem0_compat.types (POS: Mem0-wire types)

[OUTPUT]
Bidirectional conversion functions between internal MemoryItem and Mem0 wire format.

[POS]
Thin, stateless format conversion. No business logic — only data shape mapping.
"""

from __future__ import annotations

import hashlib

from app.api.mem0_compat.types import (
    Mem0MemoryItem,
    Mem0SearchResultItem,
    datetime_to_mem0_str,
)
from app.schemas.memory.crud import MemoryItem


def memory_item_to_mem0(item: MemoryItem) -> Mem0MemoryItem:
    """Convert internal MemoryItem to Mem0 wire format."""
    metadata = dict(item.metadata) if item.metadata else {}
    metadata["memory_type"] = item.memory_type
    if item.importance != 0.5:
        metadata["importance"] = item.importance
    if item.tags:
        metadata["tags"] = item.tags

    return Mem0MemoryItem(
        id=item.id,
        memory=item.content,
        hash=hashlib.md5(item.content.encode()).hexdigest(),
        metadata=metadata,
        created_at=datetime_to_mem0_str(item.created_at),
        updated_at=datetime_to_mem0_str(item.updated_at),
        user_id="sandbox",
    )


def memory_item_to_mem0_search(item: MemoryItem, score: float) -> Mem0SearchResultItem:
    """Convert internal MemoryItem + score to Mem0 search result format."""
    metadata = dict(item.metadata) if item.metadata else {}
    metadata["memory_type"] = item.memory_type
    if item.tags:
        metadata["tags"] = item.tags

    return Mem0SearchResultItem(
        id=item.id,
        memory=item.content,
        hash=hashlib.md5(item.content.encode()).hexdigest(),
        metadata=metadata,
        score=score,
        created_at=datetime_to_mem0_str(item.created_at),
        updated_at=datetime_to_mem0_str(item.updated_at),
        user_id="sandbox",
    )


def extract_content_from_messages(messages: list[dict[str, str]]) -> str:
    """Extract memory content from Mem0's messages format.

    Mem0 accepts messages in chat format; we concatenate user/assistant content
    as the memory source text. The extraction logic on our side will handle
    decomposition into typed memories.
    """
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if content:
            parts.append(content)
    return " ".join(parts)
