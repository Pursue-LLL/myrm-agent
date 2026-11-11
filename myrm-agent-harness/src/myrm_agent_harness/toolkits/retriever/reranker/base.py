"""Reranker Service Base Interface.

Abstract interface for reranking services, defining a unified reranking API.
All implementations (Cloud API, etc.) must implement this interface.

[INPUT]
- (none - standard library ABC and dataclass)

[OUTPUT]
- RerankResult: Dataclass holding index, score, and text of a reranked document
- RerankerService: Abstract base class for all reranker backends

[POS]
Reranker contract layer. Declares the abstract interface and result type that every
reranker backend must implement.

"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RerankResult:
    """Rerank result of one document."""

    index: int  # Index of the document in the input list
    score: float  # Rerank score
    text: str  # Document text


class RerankerService(ABC):
    """Abstract interface for reranking services.

    Every reranking service implementation must inherit this class and implement the abstract method.
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Rerank documents against a query.

        Args:
            query: Query text
            documents: Document texts
            top_k: Return only the top k results; None returns all

        Returns:
            Rerank results sorted by score in descending order
        """
        ...

    async def rerank_pairs(
        self,
        pairs: list[tuple[str, str]],
    ) -> list[float]:
        """Rerank query-document pairs in a batch.

        Default implementation: calls rerank once per pair.
        Subclasses can override this method to provide a more efficient batch implementation.

        Args:
            pairs: List of (query, document) pairs

        Returns:
            Rerank score of each pair
        """
        scores = []
        for query, doc in pairs:
            results = await self.rerank(query, [doc], top_k=1)
            scores.append(results[0].score if results else 0.0)
        return scores
