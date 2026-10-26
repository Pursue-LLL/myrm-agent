"""What recalling a memory leaves in a real store, and what the maintenance cycle makes of it.

A memory the agent recalls gets a use stamp (count and last-use time). Forgetting protects what
was used within the last week, so a stamp that never reaches the store lets the nightly pass
archive the very facts the agent relied on that day. These scenarios run the production entry
points (search, maintenance cycle, export) on embedded Qdrant in both storage layouts: dense
(embedding backend configured) and embeddings-less (BM25 mirror only). Only the embedding
service and the staleness-review LLM are stand-ins.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_DNS, uuid5

import pytest
import pytest_asyncio

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse.index import is_sparse_authoritative
from myrm_agent_harness.toolkits.memory._manager import MemoryManager
from myrm_agent_harness.toolkits.memory._manager.import_export import mixin as import_export_mixin
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

_DIM = 32


def _embed(text: str) -> list[float]:
    """Lexical hashing: texts sharing words get similar vectors, with no model and no network."""
    acc = [0.0] * _DIM
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.blake2b(token.encode(), digest_size=_DIM).digest()
        for i, byte in enumerate(digest):
            acc[i] += byte - 127.5
    norm = math.sqrt(sum(x * x for x in acc)) or 1.0
    return [x / norm for x in acc]


class _StubEmbeddingService:
    dimension = _DIM

    async def embed(self, text: str) -> list[float]:
        return _embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [_embed(t) for t in texts]


async def _no_staleness_decisions(system: str, prompt: str) -> str:
    return "[]"


@pytest_asyncio.fixture(params=["dense", "embeddings_less"])
async def manager(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[MemoryManager]:
    if request.param == "dense":
        with patch(
            "myrm_agent_harness.toolkits.memory.setup.get_embedding_service", return_value=_StubEmbeddingService()
        ):
            created = await create_local_memory_manager(
                tmp_path / "memory", EmbeddingConfig(model="stub/lexical-hash", api_key="unused")
            )
    else:
        created = await create_local_memory_manager(tmp_path / "memory", None)
    assert is_sparse_authoritative(created._vector) == (request.param == "embeddings_less")
    created._build_text_llm_func = lambda: _no_staleness_decisions  # type: ignore[method-assign]
    try:
        yield created
    finally:
        await created.close()


def _old_hotel(name: str) -> SemanticMemory:
    """A low-importance fact long past its own validity window: forgetting would archive it."""
    created = datetime.now(UTC) - timedelta(days=420)
    return SemanticMemory(
        id=str(uuid5(NAMESPACE_DNS, name)),
        user_id="sandbox_user",
        content=f"The user stayed at hotel {name} in Shanghai last spring",
        importance=0.15,
        access_count=1,
        created_at=created,
        updated_at=created,
        expected_valid_days=180,
    )


async def _eventually(check: Callable[[], Awaitable[bool]], *, timeout: float = 10.0) -> None:
    """Wait for the fire-and-forget use stamp to land."""
    deadline = time.monotonic() + timeout
    while not await check():
        assert time.monotonic() < deadline, "the use stamp never reached the store"
        await asyncio.sleep(0.05)


async def _stored_semantics(manager: MemoryManager, *, include_archived: bool = False) -> dict[str, SemanticMemory]:
    listed = await manager.list_memories(MemoryType.SEMANTIC, limit=100, include_archived=include_archived)
    return {m.content: m for m in listed if isinstance(m, SemanticMemory)}


async def _recall(manager: MemoryManager, query: str) -> SemanticMemory:
    hits = await manager.search(query, memory_types=[MemoryType.SEMANTIC], limit=1)
    assert len(hits) == 1
    memory = hits[0].memory
    assert isinstance(memory, SemanticMemory)

    async def stamped() -> bool:
        stored = (await _stored_semantics(manager)).get(memory.content)
        return stored is not None and stored.last_accessed_at is not None

    await _eventually(stamped)
    return memory


@pytest.mark.asyncio
async def test_recalling_a_memory_stamps_its_use_in_the_store(manager: MemoryManager) -> None:
    hotel, other = _old_hotel("quasimoto0"), _old_hotel("quasimoto1")
    await manager.store_batch([hotel, other])

    await _recall(manager, "hotel quasimoto0 Shanghai")

    stored = await _stored_semantics(manager)
    recalled, untouched = stored[hotel.content], stored[other.content]
    assert recalled.access_count == 2
    assert recalled.last_accessed_at is not None
    assert (datetime.now(UTC) - recalled.last_accessed_at).total_seconds() < 120
    assert (untouched.access_count, untouched.last_accessed_at) == (1, None)
    assert recalled.content == hotel.content
    assert recalled.updated_at == pytest.approx(hotel.updated_at, abs=timedelta(seconds=1))


@pytest.mark.asyncio
async def test_a_recalled_memory_stays_searchable_after_its_use_is_stamped(manager: MemoryManager) -> None:
    await manager.store_batch([_old_hotel("quasimoto0")])
    await _recall(manager, "hotel quasimoto0 Shanghai")

    again = await manager.search("hotel quasimoto0 Shanghai", memory_types=[MemoryType.SEMANTIC], limit=3)

    assert [h.memory.content for h in again] == [_old_hotel("quasimoto0").content]


@pytest.mark.asyncio
async def test_forgetting_spares_what_the_agent_used_and_archives_its_untouched_twin(manager: MemoryManager) -> None:
    used, twin = _old_hotel("quasimoto0"), _old_hotel("quasimoto1")
    await manager.store_batch([used, twin])
    await _recall(manager, "hotel quasimoto0 Shanghai")

    await manager.run_maintenance_cycle(force=True)

    assert set(await _stored_semantics(manager)) == {used.content}
    assert twin.content in await _stored_semantics(manager, include_archived=True)


@pytest.mark.asyncio
async def test_export_reads_every_page_of_a_real_store(manager: MemoryManager, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_export_mixin, "_EXPORT_PAGE_SIZE", 2)
    await manager.store_batch([_old_hotel(f"quasimoto{i}") for i in range(5)])
    await manager.add_rule("deploying", "run smoke tests first")
    await manager.add_rule("reviewing", "read the diff twice")
    await manager.add_rule("releasing", "tag after the checks pass")
    await manager.set_profile_attribute("name", "Alice")

    exported = await manager.export_all()

    assert len(exported["semantic"]) == 5
    assert len(exported["procedural"]) == 3
    assert len(exported["profile"]) == 1
