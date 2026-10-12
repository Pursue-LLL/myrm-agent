"""Offline MemoryManager provisioning for hermetic memory tests.

[SCOPE]
A real MemoryManager on real embedded Qdrant and SQLite stores under a caller-supplied
directory. Only the embedding transport is replaced by a deterministic, hash-derived
embedder, so tests need neither provider credentials nor network access. Qdrant's retry
backoff is zeroed: a fresh store has no sparse (BM25) collection yet, the lookup fails the
same way on every attempt, and sleeping between attempts only slows the suite. Callers must
release the embedded Qdrant singletons between cases with ``clear_embedded_stores()``.

[USAGE]
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        await manager.add_knowledge("User prefers dark mode")
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory import setup as memory_setup
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore

EMBEDDING_DIMENSION = 768


class DeterministicEmbeddingService:
    """Distinct content maps to distinct vectors, identical content to identical ones."""

    dimension = EMBEDDING_DIMENSION

    @staticmethod
    def _vector(text: str) -> list[float]:
        seed = sum(ord(ch) * (idx + 1) for idx, ch in enumerate(text)) or 1
        return [((seed * (i + 1)) % 997) / 997.0 for i in range(EMBEDDING_DIMENSION)]

    async def embed(self, text: str) -> list[float]:
        return self._vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


@asynccontextmanager
async def offline_memory_manager(
    base_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    user_id: str = "offline-user",
    approval_required: bool = False,
) -> AsyncIterator[MemoryManager]:
    monkeypatch.setattr(
        memory_setup,
        "get_embedding_service",
        lambda *_args, **_kwargs: DeterministicEmbeddingService(),
    )
    monkeypatch.setattr(QdrantVectorStore, "RETRY_BASE_DELAY", 0.0)
    manager = await create_local_memory_manager(
        base_path=base_path,
        embedding_config=EmbeddingConfig(model="local/deterministic"),
        user_id=user_id,
        approval_required=approval_required,
    )
    try:
        yield manager
    finally:
        await manager.close()
