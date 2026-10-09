"""Dual-engine hybrid search business service provider.

[POS]
Singleton service managing dual-engine FTS + vector orchestration, multi-factor re-ranking,
circuit breaker state telemetry, and graceful fallback for Server API endpoints.

[INPUT]
- collections.abc.Callable, collections.abc.Awaitable
- myrm_agent_harness.toolkits.memory (
    AdaptiveCircuitBreaker,
    CircuitState,
    DualEngineHybridSearcher,
    FallbackReason,
    HybridSearchHit,
    HybridSearchQuery,
    HybridSearchReport,
    SearchMode,
  )
- app.schemas.hybrid_search (
    CircuitBreakerStatusDTO,
    HybridSearchHitDTO,
    HybridSearchQueryDTO,
    HybridSearchReportDTO,
    HybridSearchResponseDTO,
    ResetCircuitBreakerResponseDTO,
  )

[OUTPUT]
- DualEngineHybridSearchService, get_hybrid_search_service
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    AdaptiveCircuitBreaker,
    CircuitState,
    DualEngineHybridSearcher,
    HybridSearchHit,
    HybridSearchQuery,
    HybridSearchReport,
)

from app.schemas.hybrid_search import (
    CircuitBreakerStatusDTO,
    HybridSearchHitDTO,
    HybridSearchQueryDTO,
    HybridSearchReportDTO,
    HybridSearchResponseDTO,
    ResetCircuitBreakerResponseDTO,
)

ProviderFunc = Callable[[str, int], Awaitable[list[HybridSearchHit]]]


class DualEngineHybridSearchService:
    """Service orchestrating dual-engine hybrid search with circuit-breaker protection."""

    def __init__(
        self,
        fts_provider: ProviderFunc | None = None,
        vector_provider: ProviderFunc | None = None,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        """Initialize hybrid search service with fallback-ready providers."""
        self._circuit_breaker = AdaptiveCircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=recovery_timeout_seconds,
        )
        self._fts_provider = fts_provider or self._default_mock_fts
        self._vector_provider = vector_provider or self._default_mock_vector
        self._searcher = DualEngineHybridSearcher(
            fts_provider=self._fts_provider,
            vector_provider=self._vector_provider,
            circuit_breaker=self._circuit_breaker,
        )

    def set_providers(
        self,
        fts_provider: ProviderFunc,
        vector_provider: ProviderFunc | None = None,
    ) -> None:
        """Dynamically replace or configure underlying retrieval engines."""
        self._fts_provider = fts_provider
        if vector_provider is not None:
            self._vector_provider = vector_provider
        self._searcher = DualEngineHybridSearcher(
            fts_provider=self._fts_provider,
            vector_provider=self._vector_provider,
            circuit_breaker=self._circuit_breaker,
        )

    async def search(self, query_dto: HybridSearchQueryDTO) -> HybridSearchResponseDTO:
        """Execute dual-engine hybrid retrieval, re-ranking, and report generation."""
        query = HybridSearchQuery(
            query_text=query_dto.query_text,
            top_k=query_dto.top_k,
            min_score=query_dto.min_score,
            vector_weight=query_dto.vector_weight,
            text_weight=query_dto.text_weight,
            recency_half_life_days=query_dto.recency_half_life_days,
            importance_multiplier=query_dto.importance_multiplier,
            exact_phrase_boost=query_dto.exact_phrase_boost,
            mmr_lambda=query_dto.mmr_lambda,
            max_tokens=query_dto.max_tokens,
            timeout_seconds=query_dto.timeout_seconds,
        )

        hits, report = await self._searcher.search(query)

        hit_dtos = [self._to_hit_dto(h) for h in hits]
        report_dto = self._to_report_dto(report)

        return HybridSearchResponseDTO(hits=hit_dtos, report=report_dto)

    def get_circuit_status(self) -> CircuitBreakerStatusDTO:
        """Retrieve current circuit breaker telemetry metrics."""
        return CircuitBreakerStatusDTO(
            state=self._circuit_breaker.state.value,
            failure_count=self._circuit_breaker.failure_count,
            failure_threshold=self._circuit_breaker._failure_threshold,
            recovery_timeout_seconds=self._circuit_breaker._recovery_timeout,
        )

    def reset_circuit_breaker(self) -> ResetCircuitBreakerResponseDTO:
        """Manually heal and reset circuit breaker to CLOSED status."""
        self._circuit_breaker.force_state(CircuitState.CLOSED)
        return ResetCircuitBreakerResponseDTO(
            success=True,
            message="Circuit breaker manually reset to CLOSED state",
            current_state=self._circuit_breaker.state.value,
        )

    def _to_hit_dto(self, hit: HybridSearchHit) -> HybridSearchHitDTO:
        return HybridSearchHitDTO(
            item_id=hit.item_id,
            title=hit.title,
            content=hit.content,
            score=round(hit.score, 4),
            vector_score=round(hit.vector_score, 4),
            text_score=round(hit.text_score, 4),
            created_at=hit.created_at,
            exact_match=hit.exact_match,
            metadata=hit.metadata,
        )

    def _to_report_dto(self, report: HybridSearchReport) -> HybridSearchReportDTO:
        reason_val = report.fallback_reason.value if report.fallback_reason else "none"
        return HybridSearchReportDTO(
            query_text=report.query_text,
            mode=report.mode.value,
            fallback_reason=reason_val,
            total_hits=report.total_hits,
            total_latency_ms=report.total_latency_ms,
            vector_latency_ms=report.vector_latency_ms,
            fts_latency_ms=report.fts_latency_ms,
            circuit_state=report.circuit_state.value,
        )

    async def _default_mock_fts(self, query: str, limit: int) -> list[HybridSearchHit]:
        """Built-in default FTS fallback candidate simulator."""
        tokens = query.lower().split()
        if not tokens:
            return []
        now_str = datetime.now(UTC).isoformat()
        return [
            HybridSearchHit(
                item_id=f"fts_mock_{tokens[0]}",
                title=f"FTS Knowledge: {tokens[0]}",
                content=f"System documentation and reference index for {query}",
                score=0.35,
                text_score=0.35,
                created_at=now_str,
                exact_match=True,
                metadata={"engine": "sqlite_fts5"},
            )
        ]

    async def _default_mock_vector(self, query: str, limit: int) -> list[HybridSearchHit]:
        """Built-in default Vector search candidate simulator."""
        now_str = datetime.now(UTC).isoformat()
        return [
            HybridSearchHit(
                item_id="vec_mock_semantic",
                title="Semantic Vector Memory",
                content=f"Semantic neural representation relating to: {query}",
                score=0.88,
                vector_score=0.88,
                created_at=now_str,
                metadata={"engine": "qdrant_vector"},
            )
        ]


_service_instance: DualEngineHybridSearchService | None = None


def get_hybrid_search_service() -> DualEngineHybridSearchService:
    """FastAPI dependency provider for DualEngineHybridSearchService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = DualEngineHybridSearchService()
    return _service_instance
