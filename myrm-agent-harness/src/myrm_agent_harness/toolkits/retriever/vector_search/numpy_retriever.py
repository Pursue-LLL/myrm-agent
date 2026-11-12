"""NumPy-based in-memory vector retriever.

Designed for high-performance vector retrieval over temporary document collections
(e.g., web search results, crawled content) without requiring persistence.

[INPUT]
- toolkits.retriever.embedding::EmbeddingService (POS: embedding contract: the abstract interface every embedding backend (cloud, local, cached) implements)

[OUTPUT]
- RetrievalResult: Dataclass holding retrieved Document and similarity score
- NumpyVectorRetriever: In-memory vector retriever using normalized dot-product search
- search_with_numpy_retriever: Helper function to perform one-shot in-memory vector search

[POS]
Provides RetrievalResult, NumpyVectorRetriever, search_with_numpy_retriever for ephemeral in-memory RAG.
"""

import logging
from dataclasses import dataclass

import numpy as np
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.retriever.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A retrieved document with its similarity score."""

    document: Document
    score: float


class NumpyVectorRetriever:
    """NumPy-based in-memory vector retriever.

    Vector search over temporary document collections (web search results, crawled content, etc.).
    Uses pre-normalized vectors and float32; suited to fewer than 10,000 documents.

    Performance optimizations:
    - Pre-normalized document vectors (avoids repeated computation)
    - float32 (saves 50% memory versus float64)
    - Batched matrix operations (speeds up multi-query search)
    - argpartition Top-K selection (O(n) vs O(n log n))

    Differences from Qdrant:
    - No separate process to start, zero startup overhead
    - Pure in-memory computation, suited to real-time scenarios
    - No persistence, suited to temporary data
    """

    def __init__(
        self,
        documents: list[Document],
        embeddings: EmbeddingService,
    ):
        if not documents:
            raise ValueError("Document list cannot be empty")

        self._documents = documents
        self._embeddings = embeddings
        self._doc_vectors_normalized: np.ndarray | None = None
        self._embedding_computed = False

    async def ensure_embeddings(self) -> None:
        """Make sure the document embeddings are computed and normalized."""
        if self._embedding_computed:
            return

        logger.info("Computing embeddings for %d documents...", len(self._documents))
        texts = [doc.page_content for doc in self._documents]
        doc_vectors = await self._embeddings.embed_batch(texts)

        docs_arr = np.array(doc_vectors, dtype=np.float32)
        norms = np.linalg.norm(docs_arr, axis=1, keepdims=True)
        self._doc_vectors_normalized = docs_arr / (norms + 1e-8)

        self._embedding_computed = True
        logger.info("Embeddings computed (%.2f MB)", self._doc_vectors_normalized.nbytes / 1024 / 1024)

    async def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0,
    ) -> list[RetrievalResult]:
        """Search for a single query.

        Args:
            query: Query text
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score

        Returns:
            List of retrieval results
        """
        await self.ensure_embeddings()

        if self._doc_vectors_normalized is None:
            return []

        query_vector = await self._embeddings.embed(query)
        query_arr = np.array(query_vector, dtype=np.float32)
        query_norm = query_arr / (np.linalg.norm(query_arr) + 1e-8)

        scores = self._doc_vectors_normalized @ query_norm

        if score_threshold > 0:
            mask = scores >= score_threshold
            valid_indices = np.where(mask)[0]

            if len(valid_indices) == 0:
                return []

            valid_scores = scores[mask]

            if len(valid_indices) > limit:
                top_k_local = np.argpartition(valid_scores, -limit)[-limit:]
                top_k_local = top_k_local[np.argsort(valid_scores[top_k_local])[::-1]]
                final_indices = valid_indices[top_k_local]
            else:
                final_indices = valid_indices[np.argsort(valid_scores)[::-1]]
        else:
            if len(scores) > limit:
                top_k_indices = np.argpartition(scores, -limit)[-limit:]
                final_indices = top_k_indices[np.argsort(scores[top_k_indices])[::-1]]
            else:
                final_indices = np.argsort(scores)[::-1]

        results = []
        for idx in final_indices:
            doc = self._documents[idx]
            score = float(scores[idx])
            doc.metadata["score"] = score
            results.append(RetrievalResult(document=doc, score=score))

        return results

    async def batch_search(
        self,
        queries: list[str],
        limit: int = 10,
        score_threshold: float = 0.0,
    ) -> dict[str, list[RetrievalResult]]:
        """Search for multiple queries in a batch.

        Args:
            queries: Query texts
            limit: Maximum number of results per query
            score_threshold: Minimum similarity score

        Returns:
            Retrieval results of each query, keyed by query text
        """
        if not queries:
            return {}

        await self.ensure_embeddings()

        if self._doc_vectors_normalized is None:
            return {}

        query_vectors = await self._embeddings.embed_batch(queries)

        queries_arr = np.array(query_vectors, dtype=np.float32)
        queries_norms = np.linalg.norm(queries_arr, axis=1, keepdims=True)
        queries_normalized = queries_arr / (queries_norms + 1e-8)

        similarities = queries_normalized @ self._doc_vectors_normalized.T

        results: dict[str, list[RetrievalResult]] = {}
        for i, query in enumerate(queries):
            scores = similarities[i]

            if score_threshold > 0:
                mask = scores >= score_threshold
                valid_indices = np.where(mask)[0]

                if len(valid_indices) == 0:
                    results[query] = []
                    continue

                valid_scores = scores[mask]

                if len(valid_indices) > limit:
                    top_k_local = np.argpartition(valid_scores, -limit)[-limit:]
                    top_k_local = top_k_local[np.argsort(valid_scores[top_k_local])[::-1]]
                    final_indices = valid_indices[top_k_local]
                else:
                    final_indices = valid_indices[np.argsort(valid_scores)[::-1]]
            else:
                if len(scores) > limit:
                    top_k_indices = np.argpartition(scores, -limit)[-limit:]
                    final_indices = top_k_indices[np.argsort(scores[top_k_indices])[::-1]]
                else:
                    final_indices = np.argsort(scores)[::-1]

            query_results = []
            for idx in final_indices:
                doc = self._documents[idx]
                score = float(scores[idx])
                result_doc = Document(
                    page_content=doc.page_content,
                    metadata={**doc.metadata, "score": score},
                )
                query_results.append(RetrievalResult(document=result_doc, score=score))

            results[query] = query_results

        logger.info("Batch search completed: %d queries, %d documents", len(queries), len(self._documents))
        return results


async def search_with_numpy_retriever(
    queries: list[str],
    documents: list[Document],
    embeddings: EmbeddingService,
    *,
    limit: int = 10,
    score_threshold: float = 0.0,
) -> dict[str, list[tuple[Document, float]]]:
    """Convenience function for in-memory vector search."""
    if not queries or not documents:
        return {}

    try:
        retriever = NumpyVectorRetriever(documents, embeddings)
        results = await retriever.batch_search(
            queries=queries,
            limit=limit,
            score_threshold=score_threshold,
        )

        return {query: [(r.document, r.score) for r in query_results] for query, query_results in results.items()}

    except Exception as e:
        logger.error(f"NumPy vector search failed: {e}")
        return {}
