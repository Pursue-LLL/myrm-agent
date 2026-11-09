"""HTTP flow of the memory pages on a default install: no embedding model configured.

[INPUT]
app.api.memory.router::router (POS: memory HTTP routes, mounted by the memory preset)
app.services.memory.manager_deps (POS: FastAPI dependencies that build the MemoryManager)
app.core.memory.adapters.setup::create_memory_manager (POS: real manager factory, keyword mode when embedding is None)
tests.support.memory_http_stack::memory_http_stack (POS: the real stack over a temporary storage root)

[OUTPUT]
list / filter / search / export / pending review / backup answer with 200 and real data
when the ``retrieval`` settings carry no embedding; the consolidation undo card is empty, not an error.

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
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.core.memory.adapters import setup as memory_setup
from tests.support.memory_http_stack import MemoryHttpStack, memory_http_stack, retrieval_settings

pytestmark = pytest.mark.integration

_MEMORY = "/api/v1/memory"
_UNDO = f"{_MEMORY}/command-center/consolidation/undo"


def _token() -> str:
    """A word no other test content contains, so BM25 hits identify this test's memories."""
    return "kw" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(14))


@pytest.fixture
async def keyword_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MemoryHttpStack]:
    async with memory_http_stack(tmp_path, monkeypatch, embedding=False) as stack:
        yield stack


async def _create(client: AsyncClient, memory_type: str, content: str) -> str:
    resp = await client.post(f"{_MEMORY}/", json={"memory_type": memory_type, "content": content})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["id"])


async def test_pending_review_to_search_and_backup_work_without_an_embedding(keyword_api: MemoryHttpStack) -> None:
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


async def test_the_consolidation_undo_card_is_empty_without_an_embedding_because_nothing_was_consolidated(
    keyword_api: MemoryHttpStack,
) -> None:
    """Consolidation needs the dense store, so a default install has no cycle to undo; the card must say so, not fail."""
    client = keyword_api.client
    await _create(client, "semantic", f"{_token()} a fact")

    card = await client.get(_UNDO)
    undo = await client.post(_UNDO, json={"cycle_id": "never-ran"})

    assert (card.status_code, card.json()) == (200, {"summary": None})
    assert undo.status_code == 409


async def test_a_configured_embedding_still_reaches_the_manager(
    keyword_api: MemoryHttpStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Making embedding optional must not drop it when the user did configure one."""
    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=retrieval_settings(embedding=True)),
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
