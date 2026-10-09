# [POS]: app/services/memory/hybrid_memory_service.py
# [INPUT]: SQLite database path, memory payloads, search queries
# [OUTPUT]: HybridMemoryService facade managing dual-drive hybrid memory and graceful degradation

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    DenseVectorProvider,
    DualDriveHybridMemoryEngine,
    HybridEngineStats,
    HybridMemoryItem,
    HybridSearchResult,
    RetrievalMode,
)

logger = logging.getLogger(__name__)


class HybridMemoryService:
    """Service facade coordinating local SQLite FTS5 persistence, offline synonym expansion,

    and dual-drive RRF hybrid search with graceful degradation.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        vector_provider: DenseVectorProvider | None = None,
    ) -> None:
        target_path = db_path or ":memory:"
        self._engine = DualDriveHybridMemoryEngine(
            db_path=target_path,
            dense_vector_provider=vector_provider,
        )

    @property
    def engine(self) -> DualDriveHybridMemoryEngine:
        return self._engine

    def insert_item(self, item: HybridMemoryItem) -> None:
        """Store or update a memory item in the local FTS5 database."""
        self._engine.insert_item(item)

    def delete_item(self, item_id: str) -> bool:
        """Delete item by ID."""
        return self._engine.delete_item(item_id)

    def get_item(self, item_id: str) -> HybridMemoryItem | None:
        """Retrieve memory item by ID."""
        return self._engine.get_item(item_id)

    def search(
        self,
        query: str,
        limit: int = 10,
        enable_vector: bool = True,
    ) -> tuple[list[HybridSearchResult], RetrievalMode]:
        """Perform dual-drive lexical/vector search with RRF fusion or graceful degradation."""
        return self._engine.search(
            query=query,
            limit=limit,
            enable_vector=enable_vector,
        )

    def register_synonyms(self, primary_term: str, synonyms: list[str]) -> int:
        """Register a synonym cluster and return total synonyms for the term."""
        self._engine.synonym_expander.register_synonyms(primary_term, synonyms)
        return len(self._engine.synonym_expander.get_synonyms(primary_term))

    def get_stats(self) -> HybridEngineStats:
        """Produce telemetry snapshot."""
        return self._engine.get_stats()

    def set_vector_provider(self, provider: DenseVectorProvider | None) -> None:
        """Inject or clear vector provider dynamically."""
        self._engine.set_dense_vector_provider(provider)

    def close(self) -> None:
        """Close SQLite database."""
        self._engine.close()


_hybrid_memory_service_instance: HybridMemoryService | None = None


def get_hybrid_memory_service() -> HybridMemoryService:
    """Dependency provider returning singleton HybridMemoryService instance."""
    global _hybrid_memory_service_instance
    if _hybrid_memory_service_instance is None:
        _hybrid_memory_service_instance = HybridMemoryService()
    return _hybrid_memory_service_instance
