"""
[POS] app/services/memory/zero_llm_memory_service.py
[INPUT] pathlib.Path, app/schemas/zero_llm_memory.py, myrm_agent_harness.toolkits.memory.zero_llm
[OUTPUT] ZeroLlmMemoryService, get_zero_llm_memory_service

Service layer for Zero-LLM deterministic local memory capture and FTS graph retrieval.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from myrm_agent_harness.toolkits.memory.zero_llm import (
    ExtractionBatchResult,
    ZeroLlmConfig,
    ZeroLlmMemoryEngine,
    ZeroLlmSearchResult,
)

from app.schemas.zero_llm_memory import (
    ZeroLlmExtractRequest,
    ZeroLlmExtractResponse,
    ZeroLlmFactDTO,
    ZeroLlmSearchHitDTO,
    ZeroLlmSearchRequest,
    ZeroLlmSearchResponse,
    ZeroLlmStatsResponse,
)


class ZeroLlmMemoryService:
    """Service wrapping zero-cost fact capture and local SQLite FTS5 graph search."""

    def __init__(self, engine: ZeroLlmMemoryEngine | None = None) -> None:
        if engine is not None:
            self._engine = engine
        else:
            base_dir_env = os.getenv("MYRM_WIKI_MEMORY_DIR", ".myrm/wiki_memory_data")
            db_path = Path(base_dir_env).resolve() / "derived_index.db"
            config = ZeroLlmConfig()
            self._engine = ZeroLlmMemoryEngine(db_path=db_path, config=config)

    def extract_facts(self, req: ZeroLlmExtractRequest) -> ZeroLlmExtractResponse:
        """Extract deterministic operational facts with zero LLM API cost."""
        result: ExtractionBatchResult = self._engine.extract_facts(
            text=req.text,
            turn_index=req.turn_index,
            source_file=req.source_file,
        )
        fact_dtos: list[ZeroLlmFactDTO] = [
            ZeroLlmFactDTO(
                fact_id=f.fact_id,
                category=f.category.value,
                subject=f.subject,
                predicate=f.predicate,
                object_value=f.object_value,
                confidence=f.confidence,
                evidence_snippet=f.evidence_snippet,
                source_turn_index=f.source_turn_index,
                source_file=f.source_file,
            )
            for f in result.facts
        ]
        return ZeroLlmExtractResponse(
            facts=fact_dtos,
            total_extracted=result.total_extracted,
            zero_token_cost=result.zero_token_cost,
        )

    def search(self, req: ZeroLlmSearchRequest) -> ZeroLlmSearchResponse:
        """Search memory with FTS5 lexical matching and 1-hop [[Wikilink]] graph traversal."""
        # Temporarily adapt limit/decay if requested
        self._engine.retriever.limit = req.limit
        self._engine.retriever.graph_hop_decay = req.graph_hop_decay

        result: ZeroLlmSearchResult = self._engine.search(
            query=req.query,
            profile_id=req.profile_id,
        )
        hit_dtos: list[ZeroLlmSearchHitDTO] = [
            ZeroLlmSearchHitDTO(
                page_slug=h.page_slug,
                title=h.title,
                snippet=h.snippet,
                fts_score=h.fts_score,
                graph_hops=h.graph_hops,
                composite_score=h.composite_score,
                linked_entities=h.linked_entities,
            )
            for h in result.hits
        ]
        return ZeroLlmSearchResponse(
            query=result.query,
            hits=hit_dtos,
            total_hits=result.total_hits,
            zero_token_cost=result.zero_token_cost,
        )

    def get_stats(self) -> ZeroLlmStatsResponse:
        """Return operational telemetry and zero-cost verification statistics."""
        stats = self._engine.get_stats()
        return ZeroLlmStatsResponse(
            total_extractions=int(stats["total_extractions"]),
            total_queries=int(stats["total_queries"]),
            zero_token_cost=bool(stats["zero_token_cost"]),
            augmentation_mode=str(stats["augmentation_mode"]),
            llm_available=bool(stats["llm_available"]),
            min_confidence=float(stats["min_confidence"]),
            graph_hop_decay=float(stats["graph_hop_decay"]),
        )


_ZERO_LLM_SERVICE_INSTANCE: ZeroLlmMemoryService | None = None
_ZERO_LLM_SERVICE_LOCK = threading.Lock()


def get_zero_llm_memory_service() -> ZeroLlmMemoryService:
    """Singleton provider for ZeroLlmMemoryService."""
    global _ZERO_LLM_SERVICE_INSTANCE
    if _ZERO_LLM_SERVICE_INSTANCE is None:
        with _ZERO_LLM_SERVICE_LOCK:
            if _ZERO_LLM_SERVICE_INSTANCE is None:
                _ZERO_LLM_SERVICE_INSTANCE = ZeroLlmMemoryService()
    return _ZERO_LLM_SERVICE_INSTANCE
