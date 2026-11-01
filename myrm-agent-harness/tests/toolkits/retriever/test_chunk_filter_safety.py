"""Unit tests for the ChunkFilter zero-recall safety fallback."""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.retriever.preprocessing.chunk_filter import ChunkFilter


@pytest.mark.asyncio
async def test_chunk_filter_zero_recall_and_cross_language_bounded_fallback() -> None:
    """Verify ChunkFilter fallback never exceeds max_retained_chunks and never returns empty for valid chunks."""
    filter_instance = ChunkFilter(
        long_doc_threshold=100,
        bm25_topk_ratio=2,
        max_retained_chunks=3,
        min_retained_chunks=1,
    )

    # 10 chunks created from a long document
    long_doc_text = "Detailed documentation chapter paragraph. " * 30
    doc = Document(page_content=long_doc_text, metadata={"url": "https://example.com/spec"})

    # Monolingual zero-match queries
    filtered = await filter_instance.filter_chunks_by_relevance(
        url="https://example.com/spec",
        document=doc,
        queries=["量子力学 宇宙膨胀 黑洞"],
    )

    # Must be bounded by max_retained_chunks (3), NOT 0 and NOT 10!
    assert 0 < len(filtered) <= 3
