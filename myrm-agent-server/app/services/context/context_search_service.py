"""Unified context search (memory + authorized local files).

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: memory manager)
- myrm_agent_harness.toolkits.local_file_search::LocalFileSearchEngine (POS: local file search)
- app.services.local_file_search.service::LocalFileSearchService (POS: local file search service)

[OUTPUT]
- ContextSearchService: parallel memory/workspace recall with RRF merge

[POS]
Server business layer unified context search v0 for GUI users and Agent tools.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from myrm_agent_harness.toolkits.local_file_search import LocalFileSearchEngine

from app.schemas.context.search import ContextSearchHit, ContextSearchResponse

_RRF_K = 60


@dataclass(frozen=True, slots=True)
class _RankedCandidate:
    key: str
    source: str
    title: str
    snippet: str
    reference: str
    rank: int


class ContextSearchService:
    """Search memory and authorized workspace files in one call."""

    def __init__(
        self,
        *,
        memory_manager: MemoryManager | None,
        file_engine: LocalFileSearchEngine | None,
    ) -> None:
        self._memory_manager = memory_manager
        self._file_engine = file_engine

    async def search(self, query: str, *, top_k: int = 8) -> ContextSearchResponse:
        started = time.perf_counter()
        memory_candidates: list[_RankedCandidate] = []
        file_candidates: list[_RankedCandidate] = []

        if self._memory_manager is not None:
            memory_results = await self._memory_manager.search(
                query,
                memory_types=[
                    MemoryType.SEMANTIC,
                    MemoryType.EPISODIC,
                    MemoryType.CONVERSATION,
                    MemoryType.PROCEDURAL,
                ],
                limit=top_k,
                use_rrf=True,
            )
            for rank, result in enumerate(memory_results):
                memory_candidates.append(
                    _RankedCandidate(
                        key=f"memory:{result.id}",
                        source="memory",
                        title=f"{result.memory_type.value} memory",
                        snippet=result.content[:400],
                        reference=result.id,
                        rank=rank,
                    )
                )

        if self._file_engine is not None:
            file_response = await self._file_engine.search(query, top_k=top_k)
            for rank, hit in enumerate(file_response.hits):
                file_candidates.append(
                    _RankedCandidate(
                        key=f"file:{hit.file_path}:{rank}",
                        source="workspace_file",
                        title=hit.file_path,
                        snippet=hit.snippet[:400],
                        reference=hit.file_path,
                        rank=rank,
                    )
                )

        merged = _rrf_merge([memory_candidates, file_candidates], top_k=top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return ContextSearchResponse(
            query=query,
            hits=[
                ContextSearchHit(
                    source="memory" if item.source == "memory" else "workspace_file",
                    rank=index + 1,
                    score=round(item.score, 6),
                    title=item.title,
                    snippet=item.snippet,
                    reference=item.reference,
                )
                for index, item in enumerate(merged)
            ],
            memory_count=len(memory_candidates),
            file_count=len(file_candidates),
            search_time_ms=round(elapsed_ms, 2),
        )


@dataclass(frozen=True, slots=True)
class _ScoredCandidate:
    key: str
    source: str
    title: str
    snippet: str
    reference: str
    score: float


def _rrf_merge(lists: list[list[_RankedCandidate]], *, top_k: int) -> list[_ScoredCandidate]:
    scores: dict[str, float] = {}
    payloads: dict[str, _RankedCandidate] = {}
    for candidates in lists:
        for candidate in candidates:
            payloads[candidate.key] = candidate
            scores[candidate.key] = scores.get(candidate.key, 0.0) + 1.0 / (
                _RRF_K + candidate.rank + 1
            )
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    return [
        _ScoredCandidate(
            key=key,
            source=payloads[key].source,
            title=payloads[key].title,
            snippet=payloads[key].snippet,
            reference=payloads[key].reference,
            score=score,
        )
        for key, score in ordered
    ]
