"""[INPUT]
- .base::MemorySearchBase (POS: 共享状态)
- .collection::MemoryCollectionMixin (POS: 收集阶段)
- .helpers::_elapsed_ms / _temporal_window_metadata (POS: 纯函数助手)
- .ranking::MemoryRankingMixin (POS: 排序阶段)

[OUTPUT]
- MemorySearchService: 对外检索入口

[POS]
`memory/_internal/search_service/` 的编排层；组合收集、排序与图增强并记录 trace。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from myrm_agent_harness.toolkits.memory._internal.channel_pruning import ChannelPruner
from myrm_agent_harness.toolkits.memory._internal.deadline_budget import deadline_remaining, embedding_budget
from myrm_agent_harness.toolkits.memory._internal.maintenance import enrich_with_graph
from myrm_agent_harness.toolkits.memory._internal.rerank_gate import apply_cross_rerank
from myrm_agent_harness.toolkits.memory._internal.storage import (
    embed_single,
)
from myrm_agent_harness.toolkits.memory._internal.temporal_window import TemporalWindow, derive_temporal_window
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.metrics import get_search_metrics
from myrm_agent_harness.toolkits.memory.observability import (
    GATHER_GRAPH_FAILED,
    GATHER_GRAPH_TIMEOUT,
    GATHER_QUERY_EMBEDDING_FAILED,
    GATHER_QUERY_EMBEDDING_TIMEOUT,
    GATHER_RERANK_TIMEOUT,
    JsonValue,
    MemoryRetrievalTrace,
    MemoryTraceStep,
)
from myrm_agent_harness.toolkits.memory.protocols.cache import EmbeddingCacheProtocol
from myrm_agent_harness.toolkits.memory.protocols.embedding import EmbeddingProtocol
from myrm_agent_harness.toolkits.memory.protocols.graph import GraphStoreProtocol
from myrm_agent_harness.toolkits.memory.protocols.relational import RelationalStoreProtocol
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol
from myrm_agent_harness.toolkits.memory.query_analyzer import analyze_query
from myrm_agent_harness.toolkits.memory.query_sanitizer import QuerySanitizer
from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever
from myrm_agent_harness.toolkits.memory.types import (
    MemorySearchResult,
    MemoryType,
)
from myrm_agent_harness.utils.runtime.cancellation import reraise_if_cancelled

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.retriever.reranker.base import RerankerService

from .base import FTS5SearcherFunc, MemorySearchBase
from .collection import MemoryCollectionMixin
from .helpers import _elapsed_ms, _temporal_window_metadata
from .ranking import MemoryRankingMixin

logger = logging.getLogger(__name__)



class MemorySearchService(MemoryCollectionMixin, MemoryRankingMixin, MemorySearchBase):
    """Search-side orchestrator for memory retrieval."""

    def __init__(
        self,
        *,
        namespaces: list[str],
        current_channel_id: str | None,
        config: MemoryConfig,
        vector: VectorStoreProtocol | None,
        graph: GraphStoreProtocol | None,
        relational: RelationalStoreProtocol | None,
        embedding: EmbeddingProtocol | None,
        cache: EmbeddingCacheProtocol | None,
        retriever: MemoryRetriever,
        fts5_searcher: FTS5SearcherFunc | None,
        reranker: RerankerService | None = None,
    ) -> None:
        self._namespaces = list(namespaces)
        self._current_channel_id = current_channel_id
        self._config = config
        self._vector = vector
        self._graph = graph
        self._relational = relational
        self._embedding = embedding
        self._cache = cache
        self._retriever = retriever
        self._fts5_searcher = fts5_searcher
        self._reranker = reranker
        self._last_trace: MemoryRetrievalTrace | None = None


    @property
    def last_trace(self) -> MemoryRetrievalTrace | None:
        return self._last_trace


    async def search(
        self,
        query: str,
        *,
        memory_types: list[MemoryType],
        memory_types_unspecified: bool,
        limit: int,
        use_rrf: bool,
        include_raw: bool,
        since: datetime | None = None,
        until: datetime | None = None,
        current_chat_id: str | None = None,
        dynamic_signal_weights: dict[str, float] | None = None,
    ) -> list[MemorySearchResult]:
        trace_start = perf_counter()
        steps: list[MemoryTraceStep] = []
        sanitized_query = QuerySanitizer().sanitize(query)
        steps.append(
            MemoryTraceStep(
                phase="sanitize",
                title="query_sanitize",
                summary="Retrieval query sanitized before storage lookup.",
                input_count=1 if query else 0,
                output_count=1 if sanitized_query else 0,
                metadata={"changed": sanitized_query != query},
            )
        )
        pruning_res = ChannelPruner.resolve_channels(
            self._config,
            sanitized_query,
            memory_types,
            memory_types_unspecified=memory_types_unspecified,
        )
        search_types = pruning_res.search_types
        runtime_config = pruning_res.runtime_config
        # Temporal hard-filter derivation: only when the caller passed neither
        # bound (explicit scope always wins, mirroring ChannelPruner invariance).
        effective_since, effective_until = since, until
        temporal_window: TemporalWindow | None = None
        if since is None and until is None and runtime_config.retrieval.enable_temporal_window:
            temporal_window = derive_temporal_window(sanitized_query)
            if temporal_window is not None:
                effective_since = temporal_window.since
                effective_until = temporal_window.until
        claim_requested = self._graph is not None and (
            memory_types_unspecified or MemoryType.CLAIM in memory_types or MemoryType.SEMANTIC in search_types
        )
        if dynamic_signal_weights:
            runtime_config = replace(
                runtime_config,
                retrieval=replace(
                    runtime_config.retrieval,
                    dynamic_signal_weights=dynamic_signal_weights,
                ),
            )
        tracked_types = list(dict.fromkeys([*search_types, *([MemoryType.CLAIM] if claim_requested else [])]))
        metrics = get_search_metrics()
        route_metadata: dict[str, Any] = {
            "claim_requested": claim_requested,
            "use_rrf": use_rrf,
            "intent": pruning_res.decision.intent.value if pruning_res.decision else None,
            "confidence": pruning_res.decision.confidence if pruning_res.decision else None,
            "routing_mode": pruning_res.decision.routing_mode if pruning_res.decision else "broadcast",
            "pruned_channels": [t.value for t in pruning_res.pruned_types],
            "target_subgraphs": pruning_res.decision.target_subgraphs if pruning_res.decision else [],
            "temporal_window": _temporal_window_metadata(temporal_window),
        }
        steps.append(
            MemoryTraceStep(
                phase="route",
                title="channel_routing_and_pruning",
                summary=(
                    f"Resolved {len(search_types)} search types; pruned {len(pruning_res.pruned_types)} channels."
                    if pruning_res.pruned_types
                    else "Memory types and claim graph eligibility resolved."
                ),
                input_count=len(memory_types),
                output_count=len(tracked_types),
                metadata=route_metadata,
            )
        )

        with metrics.track_search(searched_types=tracked_types, current_chat_id=current_chat_id) as tracker:
            degraded = False
            warning_codes: list[str] = []
            deadline = perf_counter() + runtime_config.retrieval.timeout_seconds
            embedding_required = self._embedding is not None and any(
                memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.CONVERSATION)
                for memory_type in search_types
            )
            embed_start = perf_counter()
            query_vector = None
            if embedding_required:
                embed_budget = embedding_budget(deadline, runtime_config.retrieval.timeout_seconds)
                try:
                    query_vector = await asyncio.wait_for(
                        self._embed_query_if_needed(sanitized_query, search_types),
                        timeout=embed_budget,
                    )
                except TimeoutError:
                    degraded = True
                    warning_codes.append(GATHER_QUERY_EMBEDDING_TIMEOUT)
                    get_search_metrics().record_degradation("timeout")
                    logger.warning(
                        "Memory query embedding timed out after %.1fs; continuing with local-only recall",
                        embed_budget,
                    )
                except BaseException as exc:
                    if isinstance(exc, asyncio.CancelledError):
                        reraise_if_cancelled(exc)
                    degraded = True
                    warning_codes.append(GATHER_QUERY_EMBEDDING_FAILED)
                    get_search_metrics().record_degradation("error")
                    logger.warning("Memory query embedding failed: %s; continuing with local-only recall", exc)
            embed_metadata: dict[str, Any] = {}
            if query_vector is None and embedding_required:
                embed_metadata["degraded"] = True
                embed_metadata["kind"] = "timeout" if GATHER_QUERY_EMBEDDING_TIMEOUT in warning_codes else "error"
                embed_metadata["warning_codes"] = [c for c in warning_codes if c.startswith("GATHER_QUERY_EMBEDDING")]
            steps.append(
                MemoryTraceStep(
                    phase="embed",
                    status="success"
                    if query_vector is not None
                    else "skipped"
                    if not embedding_required
                    else "warning",
                    title="query_embedding",
                    summary="Dense query vector prepared when vector-backed memory types are searched.",
                    duration_ms=_elapsed_ms(embed_start),
                    input_count=1,
                    output_count=1 if query_vector is not None else 0,
                    metadata=embed_metadata,
                )
            )
            collect_start = perf_counter()
            result_lists, collect_degraded, collect_warnings, source_names = await self._collect_result_lists(
                query=sanitized_query,
                memory_types=search_types,
                limit=limit,
                include_raw=include_raw,
                config=runtime_config,
                query_vector=query_vector,
                deadline=deadline,
                since=effective_since,
                until=effective_until,
            )
            degraded = degraded or collect_degraded
            warning_codes.extend(collect_warnings)
            candidate_count = sum(len(result_list) for result_list in result_lists)
            collect_metadata: dict[str, Any] = {"result_lists": len(result_lists), "sources": source_names}
            if collect_degraded:
                collect_metadata["degraded"] = True
                collect_metadata["kind"] = (
                    "timeout" if any(w.endswith("_TIMEOUT") for w in collect_warnings) else "error"
                )
            if collect_warnings:
                collect_metadata["warning_codes"] = list(collect_warnings)
            steps.append(
                MemoryTraceStep(
                    phase="collect",
                    status="warning" if collect_degraded else "success",
                    title="candidate_collect",
                    summary="Candidate memories collected from configured stores.",
                    duration_ms=_elapsed_ms(collect_start),
                    input_count=len(search_types),
                    output_count=candidate_count,
                    metadata=collect_metadata,
                )
            )
            rank_start = perf_counter()
            query_context = analyze_query(sanitized_query)
            final = self._rank_results(
                result_lists=result_lists,
                query=sanitized_query,
                limit=limit,
                use_rrf=use_rrf,
                config=runtime_config,
                query_context=query_context,
                source_names=source_names,
            )
            steps.append(
                MemoryTraceStep(
                    phase="rank",
                    title="candidate_rank",
                    summary="Candidates fused, suppressed, diversified, and normalized.",
                    duration_ms=_elapsed_ms(rank_start),
                    input_count=candidate_count,
                    output_count=len(final),
                    metadata={"limit": limit, "use_rrf": use_rrf},
                )
            )
            if self._graph is not None and claim_requested:
                graph_start = perf_counter()
                graph_degraded = False
                graph_warnings: list[str] = []
                try:
                    final = await asyncio.wait_for(
                        enrich_with_graph(
                            final,
                            sanitized_query,
                            limit,
                            self._graph,
                            self._vector,
                            runtime_config,
                            current_channel_id=self._current_channel_id,
                            namespaces=self._namespaces,
                            reraise_graph_errors=True,
                        ),
                        timeout=deadline_remaining(deadline),
                    )
                except TimeoutError:
                    graph_degraded = True
                    degraded = True
                    warning_codes.append(GATHER_GRAPH_TIMEOUT)
                    graph_warnings.append(GATHER_GRAPH_TIMEOUT)
                    get_search_metrics().record_degradation("timeout")
                    logger.warning(
                        "Memory claim graph enrichment timed out after %.1fs; skipping graph results",
                        runtime_config.retrieval.timeout_seconds,
                    )
                except BaseException as exc:
                    if isinstance(exc, asyncio.CancelledError):
                        reraise_if_cancelled(exc)
                    graph_degraded = True
                    degraded = True
                    warning_codes.append(GATHER_GRAPH_FAILED)
                    graph_warnings.append(GATHER_GRAPH_FAILED)
                    get_search_metrics().record_degradation("error")
                    logger.warning("Memory claim graph enrichment error: %s", exc)
                graph_metadata: dict[str, Any] = {}
                if graph_degraded:
                    graph_metadata["degraded"] = True
                    graph_metadata["kind"] = "timeout" if GATHER_GRAPH_TIMEOUT in graph_warnings else "error"
                    graph_metadata["warning_codes"] = graph_warnings
                steps.append(
                    MemoryTraceStep(
                        phase="graph",
                        status="warning" if graph_degraded else "success",
                        title="graph_enrich",
                        summary="Claim graph enrichment applied to retrieval candidates.",
                        duration_ms=_elapsed_ms(graph_start),
                        input_count=candidate_count,
                        output_count=len(final),
                        metadata=graph_metadata,
                    )
                )
            else:
                steps.append(
                    MemoryTraceStep(
                        phase="graph",
                        status="skipped",
                        title="graph_enrich",
                        summary="Graph enrichment skipped for this query.",
                        input_count=candidate_count,
                        output_count=len(final),
                    )
                )
            rerank_input_count = len(final)
            rerank_outcome = await apply_cross_rerank(
                final,
                sanitized_query,
                reranker=self._reranker,
                config=runtime_config,
                deadline=deadline,
            )
            final = rerank_outcome.results
            if rerank_outcome.degraded:
                degraded = True
                warning_codes.extend(rerank_outcome.warning_codes)
                get_search_metrics().record_degradation(
                    "timeout" if GATHER_RERANK_TIMEOUT in rerank_outcome.warning_codes else "error"
                )
            rerank_metadata: dict[str, JsonValue] = {
                "applied": rerank_outcome.applied,
                "degraded": rerank_outcome.degraded,
                "reranked_count": rerank_outcome.reranked_count,
                "skip_reason": rerank_outcome.skip_reason,
            }
            if rerank_outcome.warning_codes:
                rerank_metadata["warning_codes"] = list(rerank_outcome.warning_codes)
            steps.append(
                MemoryTraceStep(
                    phase="rerank",
                    status=(
                        "warning" if rerank_outcome.degraded else "success" if rerank_outcome.applied else "skipped"
                    ),
                    title="cross_rerank",
                    summary=(
                        "Cross-encoder rerank unified fused and graph scores into one relevance order."
                        if rerank_outcome.applied
                        else "Cross-encoder rerank skipped for this query."
                    ),
                    duration_ms=rerank_outcome.duration_ms,
                    input_count=rerank_input_count,
                    output_count=len(final),
                    metadata=rerank_metadata,
                )
            )
            if not include_raw:
                final = self._strip_raw_exchange(final)
            tracker.record(final)
        deduped_warning_codes = list(dict.fromkeys(warning_codes))
        self._last_trace = MemoryRetrievalTrace(
            id=uuid4().hex,
            query_preview=sanitized_query[:180],
            occurred_at=datetime.now(UTC),
            result_count=len(final),
            degraded=degraded,
            warning_codes=deduped_warning_codes,
            steps=[
                *steps,
                MemoryTraceStep(
                    phase="budget",
                    title="output_budget",
                    summary="Raw exchanges stripped when recall output requested a compact result.",
                    status="success" if not include_raw else "skipped",
                    duration_ms=_elapsed_ms(trace_start),
                    input_count=candidate_count if "candidate_count" in locals() else 0,
                    output_count=len(final),
                    metadata={"include_raw": include_raw},
                ),
            ],
        )
        return final


    async def _embed_query_if_needed(self, query: str, memory_types: list[MemoryType]) -> list[float] | None:
        needs_vector = any(
            memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.CONVERSATION)
            for memory_type in memory_types
        )
        if not needs_vector or self._embedding is None:
            return None
        return await embed_single(query, self._embedding, self._cache)
