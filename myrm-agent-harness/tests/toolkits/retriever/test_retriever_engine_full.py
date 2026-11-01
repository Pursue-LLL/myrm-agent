"""Unit tests for RetrieverManager: crawl-result strategy switch, reranking delegation and URL retrieval."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.retriever.engine import RetrieverManager


@pytest.mark.asyncio
async def test_retrieve_from_crawl_results_empty() -> None:
    """Verify retrieve_from_crawl_results returns empty tuple when crawl results are empty."""
    manager = RetrieverManager()
    dummy_reranker = MagicMock()
    dummy_embeddings = MagicMock()

    meta, text = await manager.retrieve_from_crawl_results(
        queries="test",
        reranker=dummy_reranker,
        embeddings=dummy_embeddings,
        pre_crawled_results=([], []),
    )
    assert meta == []
    assert text == ""


@pytest.mark.asyncio
async def test_retrieve_from_crawl_results_direct_and_hybrid() -> None:
    """Verify retrieve_from_crawl_results switches between direct reranking and hybrid paths."""
    manager = RetrieverManager()
    dummy_reranker = MagicMock()
    dummy_embeddings = MagicMock()

    # SuccessResult is list[tuple[str, Document]]
    sample_doc = Document(
        page_content="Guide on distributed consensus and Raft algorithm in high throughput systems.",
        metadata={"url": "https://example.com/guide", "title": "Consensus Guide"},
    )
    success_crawl = [("https://example.com/guide", sample_doc)]

    with (
        patch(
            "myrm_agent_harness.toolkits.retriever.engine.create_document_chunks_from_crawl_results",
            new=AsyncMock(return_value=[sample_doc]),
        ),
        patch(
            "myrm_agent_harness.toolkits.retriever.engine.hybrid_retriever.direct_reranking_only",
            new=AsyncMock(return_value=[sample_doc]),
        ) as mock_direct,
        patch(
            "myrm_agent_harness.toolkits.retriever.engine.format_documents_with_metadata",
            return_value=([{"url": "https://example.com/guide"}], "Formatted text", {}),
        ),
    ):
        meta, formatted = await manager.retrieve_from_crawl_results(
            queries=["raft algorithm"],
            reranker=dummy_reranker,
            embeddings=dummy_embeddings,
            pre_crawled_results=(success_crawl, []),
            hybrid_top_k_per_query=100,  # Forces direct rerank path
        )
        assert mock_direct.called
        assert meta == [{"url": "https://example.com/guide"}]
        assert formatted == "Formatted text"

        sample_docs = [
            Document(page_content=f"Doc chunk {i}", metadata={"url": f"https://example.com/{i}"}) for i in range(5)
        ]
        with (
            patch(
                "myrm_agent_harness.toolkits.retriever.engine.create_document_chunks_from_crawl_results",
                new=AsyncMock(return_value=sample_docs),
            ),
            patch(
                "myrm_agent_harness.toolkits.retriever.engine.hybrid_retriever.hybrid_retrieval_with_reranking",
                new=AsyncMock(return_value=sample_docs[:2]),
            ) as mock_hybrid,
            patch(
                "myrm_agent_harness.toolkits.retriever.engine.format_documents_with_metadata",
                return_value=([{"url": "https://example.com/guide"}], "Formatted text", {}),
            ),
        ):
            meta, formatted = await manager.retrieve_from_crawl_results(
                queries="raft algorithm",
                reranker=dummy_reranker,
                embeddings=dummy_embeddings,
                pre_crawled_results=(success_crawl, []),
                hybrid_top_k_per_query=2,  # 5 chunks > 2 -> forces hybrid retrieval path
            )
            assert mock_hybrid.called
            assert meta == [{"url": "https://example.com/guide"}]


@pytest.mark.asyncio
async def test_direct_and_hybrid_reranking_delegation() -> None:
    """Verify direct_reranking_only and hybrid_retrieval_with_reranking delegate to hybrid_retriever."""
    manager = RetrieverManager()
    dummy_reranker = MagicMock()
    docs = [Document(page_content="hello world")]

    with patch(
        "myrm_agent_harness.toolkits.retriever.engine.hybrid_retriever.direct_reranking_only",
        new=AsyncMock(return_value=docs),
    ) as mock_direct:
        res = await manager.direct_reranking_only(["q"], docs, dummy_reranker)
        assert res == docs
        assert mock_direct.called

    with patch(
        "myrm_agent_harness.toolkits.retriever.engine.hybrid_retriever.hybrid_retrieval_with_reranking",
        new=AsyncMock(return_value=docs),
    ) as mock_hybrid:
        res = await manager.hybrid_retrieval_with_reranking(["q"], docs, dummy_reranker, MagicMock())
        assert res == docs
        assert mock_hybrid.called


@pytest.mark.asyncio
async def test_retrieve_from_urls_validation_and_flow() -> None:
    """Verify retrieve_from_urls validates arguments, handles failures, and executes successfully."""
    manager = RetrieverManager()
    dummy_reranker = MagicMock()
    dummy_embeddings = MagicMock()

    # Empty URLs
    meta, ctx, err = await manager.retrieve_from_urls([], "query", dummy_reranker, dummy_embeddings)
    assert err == "No URLs provided"
    assert meta == []

    # Empty queries
    meta, ctx, err = await manager.retrieve_from_urls(["https://a.com"], "", dummy_reranker, dummy_embeddings)
    assert err == "No queries provided"

    # Crawl failure
    with patch(
        "myrm_agent_harness.toolkits.web_fetch.FetchEngine.crawl_many",
        new=AsyncMock(return_value=([], [("https://fail.com", "Timeout")])),
    ):
        meta, ctx, err = await manager.retrieve_from_urls(
            ["https://fail.com"], "query", dummy_reranker, dummy_embeddings
        )
        assert "Failed to crawl URLs" in err

    # Crawl success
    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.FetchEngine.crawl_many",
            new=AsyncMock(return_value=([MagicMock()], [])),
        ),
        patch.object(
            manager,
            "retrieve_from_crawl_results",
            new=AsyncMock(return_value=([{"url": "https://ok.com"}], "Context ok")),
        ),
    ):
        meta, ctx, err = await manager.retrieve_from_urls(["https://ok.com"], "query", dummy_reranker, dummy_embeddings)
        assert err == ""
        assert meta == [{"url": "https://ok.com"}]
        assert ctx == "Context ok"

    # Exception path
    with patch(
        "myrm_agent_harness.toolkits.web_fetch.FetchEngine.crawl_many",
        new=AsyncMock(side_effect=RuntimeError("Simulated socket error")),
    ):
        meta, ctx, err = await manager.retrieve_from_urls(
            ["https://crash.com"], "query", dummy_reranker, dummy_embeddings
        )
        assert "Retrieve from URLs failed" in err
