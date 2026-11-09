"""A memory HTTP stack on a temporary directory: the real handlers, manager, embedded Qdrant and SQLite.

[INPUT]
app.core.memory.adapters.setup::create_memory_manager (POS: real manager factory; keyword mode when the embedding is None)
tests.support.minimal_app::build_minimal_app (POS: memory-preset FastAPI app)

[OUTPUT]
MemoryHttpStack: the HTTP client, the embedding configs the factory saw, the manager it built
memory_http_stack(): builds the stack and releases every store on exit
retrieval_settings(): the slice of ``UserConfigs`` the platform retrieval loader reads

[POS]
Shared by the memory HTTP suites that must not override the manager dependencies, which is what the
handler-level suites do and why they cannot see a deployment that fails to build its manager. Only the
settings store, the platform LLM, the embedding backend and the storage root are redirected.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.retriever.embedding.base import EmbeddingService
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore

from app.api.dependencies import get_deploy_identity
from app.api.memory.operations.backup import get_backup_store
from app.core.memory.adapters import setup as memory_setup
from app.services.memory.backup.volume_store import VolumeBackupStore
from tests.support.minimal_app import build_minimal_app


def retrieval_settings(*, embedding: bool) -> SimpleNamespace:
    """The slice of ``UserConfigs`` the platform retrieval loader reads."""
    retrieval: dict[str, object] | None = None
    if embedding:
        retrieval = {
            "embeddingApplied": True,
            "embeddingConfig": {"model": "BAAI/bge-m3", "apiKey": "sk-unit", "apiBase": "http://127.0.0.1:9/v1"},
        }
    return SimpleNamespace(retrieval_dict=retrieval)


@dataclass
class MemoryHttpStack:
    client: AsyncClient
    embeddings_seen: list[EmbeddingConfig | None] = field(default_factory=list)

    @staticmethod
    def manager() -> MemoryManager:
        """The one manager the API built; it is cached, so every request after the first reuses it."""
        managers = list(memory_setup._memory_manager_cache.values())
        assert len(managers) == 1, f"expected one cached manager, found {len(managers)}"
        return managers[0]


@asynccontextmanager
async def memory_http_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    embedding: bool,
    embedder: EmbeddingService | None = None,
    platform_llm: object | None = None,
) -> AsyncIterator[MemoryHttpStack]:
    """Serve the memory routes over real storage under ``tmp_path``.

    ``embedding`` puts an embedding model in the retrieval settings, so the manager is dense; ``embedder`` stands in
    for the network backend that config would otherwise reach; ``platform_llm`` is the model the platform hands the
    manager for deduplication and consolidation.
    """
    await clear_embedded_stores()
    monkeypatch.setattr(QdrantVectorStore, "RETRY_BASE_DELAY", 0.0)

    real_create = memory_setup.create_memory_manager
    embeddings_seen: list[EmbeddingConfig | None] = []

    async def isolated_create(binding, embedding_config, **kwargs):  # noqa: ANN001, ANN003, ANN202
        embeddings_seen.append(embedding_config)
        return await real_create(binding, embedding_config, base_path=tmp_path / "memory", **kwargs)

    monkeypatch.setattr(memory_setup, "create_memory_manager", isolated_create)
    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=retrieval_settings(embedding=embedding)),
    )
    monkeypatch.setattr(
        "app.services.memory.extract_retry.resolve_chat_extraction_llm.get_platform_dedup_llm",
        AsyncMock(return_value=platform_llm),
    )
    if embedder is not None:
        monkeypatch.setattr("myrm_agent_harness.toolkits.memory.setup.get_embedding_service", lambda config: embedder)

    app = build_minimal_app(preset="memory")
    app.dependency_overrides[get_deploy_identity] = lambda: "test_user"
    app.dependency_overrides[get_backup_store] = lambda: VolumeBackupStore(tmp_path / "backups")
    transport = ASGITransport(app=app)
    try:
        with patch("app.api.memory.test_seed.is_local_mode", return_value=True):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield MemoryHttpStack(client=client, embeddings_seen=embeddings_seen)
    finally:
        for manager in list(memory_setup._memory_manager_cache.values()):
            await manager.close()
        memory_setup._memory_manager_cache.clear()
        await clear_embedded_stores()
