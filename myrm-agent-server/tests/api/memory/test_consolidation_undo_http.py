"""HTTP flow of the consolidation undo card on an install that has an embedding model.

[INPUT]
app.api.memory.operations.command_center_consolidation::router (POS: the undo card endpoints)
tests.support.memory_http_stack::memory_http_stack (POS: the real stack over a temporary storage root)
myrm_agent_harness.toolkits.memory.MemoryManager::run_maintenance_cycle (POS: what the idle worker calls to run a consolidation cycle)

[OUTPUT]
A maintenance cycle that merges two memories leaves a card; its undo puts both originals back as the memory page
showed them, keeps what the user edited since, and cannot be replayed.

[POS]
Real-stack guard for the undo feature. The handlers, manager, embedded Qdrant, SQLite and the maintenance cycle are
the real ones; only the models are scripted: an embedder that gives every text its own direction and a
consolidation model that answers with the merge the test hands it.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from httpx import AsyncClient
from langchain_core.messages import BaseMessage
from myrm_agent_harness.runtime.cognitive_clock.signals import CooperativePauseSignal
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import ConsolidationResponse, MergeOp
from myrm_agent_harness.toolkits.retriever.embedding.base import EmbeddingService
from pydantic import BaseModel

from tests.support.memory_http_stack import MemoryHttpStack, memory_http_stack

pytestmark = pytest.mark.integration

_MEMORY = "/api/v1/memory"
_UNDO = f"{_MEMORY}/command-center/consolidation/undo"
_FIRST = "Mina drinks green tea every morning"
_SECOND = "Mina likes green tea early in the day"
_MERGED = "Mina drinks green tea in the morning"
_CARD_FIELDS = {"cycle_id", "recorded_at", "merged", "corrected", "updated", "change_count", "conflict_count"}

# What the memory page shows of a memory that a cycle can change: content, importance, metadata.
type Shown = tuple[str, float, dict[str, object]]


class _DirectionalEmbedder(EmbeddingService):
    """Each distinct text points its own way, so no two memories look like duplicates of each other."""

    @property
    def dimension(self) -> int:
        return 32

    async def embed(self, text: str) -> list[float]:
        spread = [byte - 127.5 for byte in hashlib.sha256(text.encode()).digest()]
        length = math.sqrt(sum(value * value for value in spread))
        return [value / length for value in spread]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


class _ScriptedConsolidator:
    """Answers every consolidation request with the operations it was last given."""

    def __init__(self) -> None:
        self._response = ConsolidationResponse(operations=[])
        self.requests = 0

    def merge(self, first_id: str, second_id: str, merged_content: str) -> None:
        self._response = ConsolidationResponse(
            operations=[MergeOp(source_ids=[first_id[:8], second_id[:8]], merged_content=merged_content)]
        )

    def with_structured_output(self, schema: type[BaseModel]) -> _ScriptedConsolidator:
        return self

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> ConsolidationResponse:
        self.requests += 1
        return self._response


@pytest.fixture
def consolidator() -> _ScriptedConsolidator:
    return _ScriptedConsolidator()


@pytest.fixture
async def dense_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, consolidator: _ScriptedConsolidator
) -> AsyncIterator[MemoryHttpStack]:
    async with memory_http_stack(
        tmp_path, monkeypatch, embedding=True, embedder=_DirectionalEmbedder(), platform_llm=consolidator
    ) as stack:
        yield stack


async def _create(client: AsyncClient, content: str) -> str:
    resp = await client.post(f"{_MEMORY}/", json={"memory_type": "semantic", "content": content})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["id"])


async def _shown(client: AsyncClient) -> dict[str, Shown]:
    """The semantic memories the memory page lists, by id."""
    resp = await client.get(f"{_MEMORY}/", params={"type": "semantic"})
    assert resp.status_code == 200, resp.text
    return {item["id"]: (item["content"], item["importance"], item["metadata"]) for item in resp.json()["items"]}


async def _merge_two_memories(stack: MemoryHttpStack, consolidator: _ScriptedConsolidator) -> dict[str, Shown]:
    """Create two memories, let one real maintenance cycle merge them, and return what the page showed before."""
    first = await _create(stack.client, _FIRST)
    second = await _create(stack.client, _SECOND)
    before = await _shown(stack.client)
    assert set(before) == {first, second}
    consolidator.merge(first, second, _MERGED)

    # The process-wide pause signal is shared state: a user who was typing in an earlier test would make the cycle yield.
    report = await stack.manager().run_maintenance_cycle(force=True, pause_signal=CooperativePauseSignal())

    assert (report.consolidation_merged, report.consolidation_errors) == (1, 0)
    return before


async def test_undoing_a_cycle_that_merged_two_memories_puts_both_back_as_they_were(
    dense_api: MemoryHttpStack, consolidator: _ScriptedConsolidator
) -> None:
    client = dense_api.client
    before = await _merge_two_memories(dense_api, consolidator)

    during = await _shown(client)
    assert sorted(content for content, _, _ in during.values()) == sorted([_FIRST, _SECOND, _MERGED])
    assert {during[memory_id][1] for memory_id in before} == {0.05}, "the merged sources are demoted, not removed"
    card = (await client.get(_UNDO)).json()["summary"]
    assert set(card) == _CARD_FIELDS, "the settings page reads exactly these fields"
    assert (card["merged"], card["corrected"], card["updated"]) == (1, 0, 0)
    assert (card["change_count"], card["conflict_count"]) == (3, 0)

    undone = await client.post(_UNDO, json={"cycle_id": card["cycle_id"]})

    assert (undone.status_code, undone.json()) == (200, {"rolled_back": 3, "skipped_conflict": 0, "errors": 0})
    assert await _shown(client) == before
    assert (await client.post(_UNDO, json={"cycle_id": card["cycle_id"]})).status_code == 409
    assert (await client.get(_UNDO)).json() == {"summary": None}
    assert dense_api.embeddings_seen and dense_api.embeddings_seen[0] is not None
    assert consolidator.requests == 1


async def test_what_the_user_edited_after_the_cycle_survives_its_undo(
    dense_api: MemoryHttpStack, consolidator: _ScriptedConsolidator
) -> None:
    client = dense_api.client
    before = await _merge_two_memories(dense_api, consolidator)
    (merged_id,) = set(await _shown(client)) - set(before)
    edited = "Mina has green tea at breakfast"
    resp = await client.put(f"{_MEMORY}/semantic/{merged_id}", json={"content": edited})
    assert resp.status_code == 200, resp.text

    card = (await client.get(_UNDO)).json()["summary"]
    undone = await client.post(_UNDO, json={"cycle_id": card["cycle_id"]})

    assert card["conflict_count"] == 1
    assert (undone.status_code, undone.json()) == (200, {"rolled_back": 2, "skipped_conflict": 1, "errors": 0})
    after = await _shown(client)
    assert after.pop(merged_id)[0] == edited
    assert after == before
