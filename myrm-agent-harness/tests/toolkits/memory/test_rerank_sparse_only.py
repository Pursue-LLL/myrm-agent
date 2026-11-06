"""Cross-encoder rerank over keyword-mode candidates (no embedding backend configured).

A user can configure a reranker without an embedding model, so the memory search
must run the rerank gate on the BM25 candidates of an embeddings-less manager and
let the reranker decide the order. The reranker here is a scripted stub that
prefers one document the keyword ranking does not put first, so a reorder can
only come from the gate.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import SemanticMemory
from myrm_agent_harness.toolkits.retriever.reranker.base import RerankerService, RerankResult
from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

QUERY = "deployment checklist"
PREFERRED_MARKER = "rollback"

# The first document repeats the query terms, so keyword ranking puts it first; the preferred
# (last) document ties with the middle ones behind it.
CONTENTS = [
    "deployment checklist deployment checklist step one",
    "deployment checklist step two",
    "deployment checklist reminder for the whole team",
    "checklist for every deployment",
    "rollback plan owner is Alice and the deployment checklist exists somewhere in the long runbook",
]
PREFERRED = CONTENTS[-1]


class MarkerReranker(RerankerService):
    """Scores a pair high when the document carries the marker; records every batch it is asked to score."""

    def __init__(self) -> None:
        self.pairs_batches: list[list[tuple[str, str]]] = []

    async def rerank(self, query: str, documents: list[str], top_k: int | None = None) -> list[RerankResult]:
        raise AssertionError("the gate scores through rerank_pairs")

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.pairs_batches.append(list(pairs))
        return [1.0 if PREFERRED_MARKER in document else 0.1 for _, document in pairs]


async def _keyword_manager(
    directory: Path, reranker: MarkerReranker | None, monkeypatch: pytest.MonkeyPatch
) -> MemoryManager:
    """An embeddings-less manager holding the fixed memories, with the stub reranker when one is given.

    Fixed ids keep the order of equally scored keyword hits identical across managers.
    """
    config = None
    if reranker is not None:
        monkeypatch.setattr("myrm_agent_harness.toolkits.memory.setup.get_reranker_service", lambda _config: reranker)
        config = RerankerConfig(model="stub/rerank", api_key="stub-key")
    manager = await create_local_memory_manager(directory, None, reranker_config=config)
    for number, content in enumerate(CONTENTS, start=1):
        await manager.store(SemanticMemory(id=str(UUID(int=number)), user_id="sandbox_user", content=content))
    return manager


async def _search_contents(manager: MemoryManager) -> list[str]:
    return [hit.memory.content for hit in await manager.search(QUERY, limit=10)]


@pytest.mark.slow
async def test_reranker_reorders_keyword_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain = await _keyword_manager(tmp_path / "plain", None, monkeypatch)
    try:
        keyword_order = await _search_contents(plain)
    finally:
        await plain.close()
    assert keyword_order[0] == CONTENTS[0]
    assert sorted(keyword_order) == sorted(CONTENTS)

    reranker = MarkerReranker()
    reranked = await _keyword_manager(tmp_path / "reranked", reranker, monkeypatch)
    try:
        reranked_order = await _search_contents(reranked)
    finally:
        await reranked.close()

    assert reranked_order[0] == PREFERRED
    # A stable sort moves only what the reranker prefers; the rest keep their keyword order.
    assert reranked_order[1:] == [content for content in keyword_order if content != PREFERRED]
    assert len(reranker.pairs_batches) == 1
    assert {document for _, document in reranker.pairs_batches[0]} == set(CONTENTS)
