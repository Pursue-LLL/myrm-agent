"""HTTP flow of the memory pages on a default install: no embedding model configured.

[INPUT]
app.api.memory.router::router (POS: memory HTTP routes, mounted by the memory preset)
app.services.memory.manager_deps (POS: FastAPI dependencies that build the MemoryManager)
app.core.memory.adapters.setup::create_memory_manager (POS: real manager factory, keyword mode when embedding is None)

[OUTPUT]
list / filter / search / export / pending review / backup answer with 200 and real data
when the ``retrieval`` settings carry no embedding.

[POS]
Regression guard for the human-facing leg of keyword mode. The dependencies, handlers, manager,
embedded Qdrant (BM25 mirrors) and SQLite are the real ones. Only the settings store (no embedding)
and the storage root (a temporary directory) are redirected; the manager dependencies themselves
are never overridden, which is what the handler-level suites do and why they could not see the 503.
"""

from __future__ import annotations

import secrets
import string
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore

from app.api.dependencies import get_deploy_identity
from app.api.memory.operations.backup import get_backup_store
from app.core.memory.adapters import setup as memory_setup
from app.services.memory.backup.volume_store import VolumeBackupStore
from tests.support.minimal_app import build_minimal_app

pytestmark = pytest.mark.integration

_MEMORY = "/api/v1/memory"


def _token() -> str:
    """A word no other test content contains, so BM25 hits identify this test's memories."""
    return "kw" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(14))


def _retrieval_settings(*, embedding: bool) -> SimpleNamespace:
    """The slice of ``UserConfigs`` the platform retrieval loader reads."""
    retrieval: dict[str, object] | None = None
    if embedding:
        retrieval = {
            "embeddingApplied": True,
            "embeddingConfig": {"model": "BAAI/bge-m3", "apiKey": "sk-unit", "apiBase": "http://127.0.0.1:9/v1"},
        }
    return SimpleNamespace(retrieval_dict=retrieval)


@dataclass
class KeywordApi:
    client: AsyncClient
    embeddings_seen: list[EmbeddingConfig | None] = field(default_factory=list)


@pytest.fixture
async def keyword_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[KeywordApi]:
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
        AsyncMock(return_value=_retrieval_settings(embedding=False)),
    )
    monkeypatch.setattr(
        "app.services.memory.extract_retry.resolve_chat_extraction_llm.get_platform_dedup_llm",
        AsyncMock(return_value=None),
    )

    app = build_minimal_app(preset="memory")
    app.dependency_overrides[get_deploy_identity] = lambda: "test_user"
    app.dependency_overrides[get_backup_store] = lambda: VolumeBackupStore(tmp_path / "backups")
    transport = ASGITransport(app=app)
    with patch("app.api.memory.test_seed.is_local_mode", return_value=True):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield KeywordApi(client=client, embeddings_seen=embeddings_seen)

    for manager in list(memory_setup._memory_manager_cache.values()):
        await manager.close()
    memory_setup._memory_manager_cache.clear()
    await clear_embedded_stores()


async def _create(client: AsyncClient, memory_type: str, content: str) -> str:
    resp = await client.post(f"{_MEMORY}/", json={"memory_type": memory_type, "content": content})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["id"])


async def test_pending_review_to_search_and_backup_work_without_an_embedding(keyword_api: KeywordApi) -> None:
    client = keyword_api.client
    word = _token()
    target_id = await _create(client, "semantic", f"{word} original fact")

    # Review queue: a proposal queued against the stored memory is listed, then approved.
    seeded = await client.post(
        f"{_MEMORY}/test/seed-pending-proposal",
        json={"content": f"{word} corrected fact", "resolution_action": "correct", "target_memory_id": target_id},
    )
    assert seeded.status_code == 200, seeded.text
    pending_id = seeded.json()["pending_id"]

    pending = await client.get(f"{_MEMORY}/pending")
    assert pending.status_code == 200, pending.text
    assert [item["id"] for item in pending.json()["items"]] == [pending_id]

    approved = await client.post(f"{_MEMORY}/pending/{pending_id}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert (await client.get(f"{_MEMORY}/pending")).json()["items"] == []

    # Memory page: list, search and the type filter all answer from the BM25 mirrors.
    listed = await client.get(f"{_MEMORY}/", params={"type": "semantic"})
    assert listed.status_code == 200, listed.text
    assert any(word in item["content"] for item in listed.json()["items"])

    searched = await client.get(f"{_MEMORY}/", params={"search": word})
    assert searched.status_code == 200, searched.text
    assert any(word in item["content"] for item in searched.json()["items"])

    direct = await client.get(f"{_MEMORY}/search", params={"query": word})
    assert direct.status_code == 200, direct.text
    assert direct.json()["total"] >= 1

    # A type nobody has written yet lists empty: its mirror collection does not exist yet.
    unwritten = await client.get(f"{_MEMORY}/", params={"type": "episodic"})
    assert unwritten.status_code == 200, unwritten.text
    assert not any(word in item["content"] for item in unwritten.json()["items"])

    exported = await client.get(f"{_MEMORY}/export")
    assert exported.status_code == 200, exported.text
    assert word in str(exported.json()["data"])

    backup = await client.post(f"{_MEMORY}/backup/create", json={"description": "keyword mode"})
    assert backup.status_code == 200, backup.text
    assert backup.json()["success"] is True
    assert backup.json()["metadata"]["memory_count"] >= 1
    assert len((await client.get(f"{_MEMORY}/backup/list")).json()["backups"]) == 1

    assert keyword_api.embeddings_seen
    assert all(cfg is None for cfg in keyword_api.embeddings_seen)


async def test_a_configured_embedding_still_reaches_the_manager(keyword_api: KeywordApi, monkeypatch: pytest.MonkeyPatch) -> None:
    """Making embedding optional must not drop it when the user did configure one."""
    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=_retrieval_settings(embedding=True)),
    )
    created: list[EmbeddingConfig | None] = []

    async def record(binding, embedding_config, **kwargs):  # noqa: ANN001, ANN003, ANN202
        created.append(embedding_config)
        raise RuntimeError("stop before touching a real embedding backend")

    monkeypatch.setattr(memory_setup, "create_memory_manager", record)

    resp = await keyword_api.client.get(f"{_MEMORY}/", params={"type": "semantic"})

    assert resp.status_code == 503
    assert len(created) == 1
    assert created[0] is not None
    assert created[0].api_key == "sk-unit"
