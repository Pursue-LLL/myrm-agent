"""Integration tests: command-center runtime vector persistence (real harness assembly).

Validates the full real chain for ``MemoryCommandCenterService._build_vector_persistence``:

- A writable embedded Qdrant store reports ``"persistent"``.
- An unwritable path that degrades to ``:memory:`` reports ``"memory_fallback"``.
- A manager without a vector store reports ``"unavailable"``.

The vector store is a *real* embedded Qdrant instance (no mock on the
persistence contract). Only the memory DB is an in-memory SQLite session,
which the runtime panel never touches.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.vector.qdrant.factory import (
    clear_embedded_stores,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.memory.command_center.command_center import MemoryCommandCenterService

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _clear_embedded_cache():
    """Release real embedded Qdrant singletons between cases."""
    await clear_embedded_stores()
    yield
    await clear_embedded_stores()


@pytest.fixture
async def db_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")


@pytest.mark.asyncio
async def test_writable_store_reports_persistent(db_factory, tmp_path: Path) -> None:
    """Real embedded Qdrant on a writable path is durable."""
    base_path = tmp_path / "memory"
    manager = await create_local_memory_manager(
        base_path=str(base_path),
        embedding_config=_embedding_config(),
    )
    try:
        assert manager.has_vector is True
        assert manager.vector_is_persistent is True

        async with db_factory() as db:
            service = MemoryCommandCenterService(db, manager)
            assert service._build_vector_persistence() == "persistent"
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_unwritable_store_reports_memory_fallback(db_factory, tmp_path: Path) -> None:
    """Unwritable vector path degrades to :memory: and is flagged as fallback."""
    blocker = tmp_path / "blocker"
    blocker.write_text("occupied")
    bad_path = blocker / "vector_store"

    manager = await create_local_memory_manager(
        base_path=str(tmp_path / "memory"),
        embedding_config=_embedding_config(),
        vector_store=await _fallback_store(str(bad_path)),
    )
    try:
        assert manager.has_vector is True
        assert manager.vector_is_persistent is False

        async with db_factory() as db:
            service = MemoryCommandCenterService(db, manager)
            assert service._build_vector_persistence() == "memory_fallback"
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_without_vector_store_reports_unavailable(db_factory) -> None:
    """Manager without vector backend reports unavailable (no data to lose)."""
    manager = MemoryManager(
        MemoryConfig(embedding_model="openai/text-embedding-3-small"),
        user_id="test_user",
        embedding=_FakeEmbedding(),
    )
    try:
        assert manager.has_vector is False
        assert manager.vector_is_persistent is True

        async with db_factory() as db:
            service = MemoryCommandCenterService(db, manager)
            assert service._build_vector_persistence() == "unavailable"
    finally:
        await manager.close()


async def _fallback_store(path: str):
    from myrm_agent_harness.toolkits.vector.qdrant.factory import create_embedded_store

    store = await create_embedded_store(path=path)
    assert store.config.local_path == ":memory:"
    assert store.is_persistent is False
    return store


class _FakeEmbedding:
    dimension = 768

    async def embed(self, text: str) -> list[float]:
        return [0.1] * 768

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 768 for _ in texts]
