"""Service provider for embedded SQLite vector storage engine.

[POS]
Orchestrates singleton lifecycle, filesystem resolution, health telemetry,
and retrieval dispatch for single-file embedded SQLite vector storage.

[INPUT]
- pathlib.Path, os
- myrm_agent_harness.toolkits.vector.sqlite_vec (SqliteVecConfig, SqliteVecStore)
- app.schemas.sqlite_vec (SqliteVecStatsResponse, SqliteVecSearchResponse, SqliteVecSearchItem)

[OUTPUT]
- SqliteVecProvider: Singleton provider managing embedded vector database instance
- get_sqlite_vec_provider: Factory function for dependency injection
"""

from __future__ import annotations

import os

from myrm_agent_harness.toolkits.vector import (
    SqliteVecConfig,
    SqliteVecStore,
)

from app.schemas.sqlite_vec import (
    SqliteVecSearchItem,
    SqliteVecSearchResponse,
    SqliteVecStatsResponse,
)


class SqliteVecProvider:
    """Manages embedded SQLite vector database lifecycle and metrics."""

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize provider with resolved database path."""
        resolved = db_path or os.getenv("SQLITE_VEC_DB_PATH", "./data/memory_vector.db")
        self.config: SqliteVecConfig = SqliteVecConfig(db_path=resolved)
        self.store: SqliteVecStore = SqliteVecStore(self.config)

    async def get_stats(self) -> SqliteVecStatsResponse:
        """Collect operational metrics from vector store."""
        db_file = self.config.resolved_path()
        file_size = db_file.stat().st_size if db_file.exists() else 0

        collections = await self.store.list_collections()
        total_docs = 0
        for col in collections:
            cnt = await self.store.count(col)
            total_docs += cnt

        healthy = await self.store.health_check()
        status_text = "healthy" if healthy else "degraded"

        return SqliteVecStatsResponse(
            engine_mode=self.store.engine_mode.value,
            is_persistent=self.store.is_persistent,
            db_path=str(db_file),
            file_size_bytes=file_size,
            collection_count=len(collections),
            total_documents=total_docs,
            status=status_text,
        )

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        apply_decay: bool = True,
        half_life_seconds: float | None = None,
        score_threshold: float | None = None,
    ) -> SqliteVecSearchResponse:
        """Execute vector search with optional temporal decay."""
        await self.store.ensure_collection(collection, dimension=len(query_vector))

        items: list[SqliteVecSearchItem] = []
        if apply_decay:
            decayed_results = await self.store.search_decayed(
                collection=collection,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                half_life_seconds=half_life_seconds,
            )
            for res in decayed_results:
                items.append(
                    SqliteVecSearchItem(
                        id=res.document.id,
                        content=res.document.content,
                        score=res.decayed_score,
                        raw_similarity=res.raw_similarity,
                        decay_factor=res.decay_factor,
                        metadata=res.document.metadata,
                    )
                )
        else:
            raw_results = await self.store.search(
                collection=collection,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
            )
            for raw in raw_results:
                items.append(
                    SqliteVecSearchItem(
                        id=raw.document.id,
                        content=raw.document.content,
                        score=raw.score,
                        raw_similarity=raw.score,
                        decay_factor=1.0,
                        metadata=raw.document.metadata,
                    )
                )

        return SqliteVecSearchResponse(
            collection=collection,
            count=len(items),
            items=items,
        )

    async def health_check(self) -> bool:
        """Verify vector store health."""
        return await self.store.health_check()

    async def close(self) -> None:
        """Release underlying resources."""
        await self.store.close()


_provider_instance: SqliteVecProvider | None = None


def get_sqlite_vec_provider() -> SqliteVecProvider:
    """Dependency injection factory for SqliteVecProvider singleton."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = SqliteVecProvider()
    return _provider_instance
