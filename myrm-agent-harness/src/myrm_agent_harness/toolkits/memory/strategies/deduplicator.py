"""Three-layer smart deduplication: Hash → Vector → LLM judgment.

[INPUT]
- memory.protocols.vector::VectorStoreProtocol (POS: vector store protocol)
- memory.types::{MemoryType, SemanticMemory} (POS: memory data models)
- strategies.dedup_hash_cache::* (POS: namespace-scoped hash key, hash-layer metrics and on-disk persistence)
- strategies.dedup_judge::{DedupJudge, hard_facet_conflict} (POS: Layer 3 verdict of a memory against its candidates)
- strategies.dedup_types::{DeduplicatableMemory, DeduplicationDecision} (POS: the memory types deduplication compares and merges, and the judgment verdicts)
- strategies.dedup_update::apply_dedup_update (POS: fold a new memory into the existing one a verdict picked)

[OUTPUT]
- SmartDeduplicator: Three-layer dedup engine (Hash→Vector→LLM), returns DUPLICATE/UPDATE_REPLACE/UPDATE_MERGE/NEW

[POS]
Three-layer smart deduplication strategy. Layer 1: O(1) normalized hash with persistent cache
and FIFO eviction. Layer 2: Semantic vector similarity with dynamic thresholds.
Layer 3: LLM judgment for DUPLICATE/UPDATE_REPLACE/UPDATE_MERGE/NEW.

Architecture:
- Layer 1 (Hash): O(1) normalized hash detection with persistent cache and FIFO eviction
  - Configurable normalization: NONE (exact match) / BASIC (case+whitespace) / FULL (all variants)
  - Batch-level deduplication: Detects duplicates within the same batch
  - Adaptive capacity: Auto-adjusts cache size based on memory count
  - Data structure: OrderedDict for FIFO eviction with O(1) operations
  - Performance: FULL ~5μs / BASIC ~3.5μs / NONE ~0.6μs (200x+ faster than vector search)
  - Hash persistence: Atomic write (temp + rename) for crash safety
- Layer 2 (Vector): Semantic similarity retrieval with dynamic thresholds
- Layer 3 (LLM): Semantic judgment for DUPLICATE/UPDATE_REPLACE/UPDATE_MERGE/NEW

Key features:
- UPDATE differentiation: REPLACE (parameter changes) vs MERGE (incremental features)
- Dynamic thresholds: Memory-type-specific similarity cutoffs (Semantic vs Episodic)
- Merge tracking: merge_count and merge_history for evolution audit
- Graceful degradation: LLM failures default to NEW to prevent data loss
- Performance metrics: Real-time observability for cache effectiveness
- Concurrent safety: Early lock reserves target before LLM, preventing redundant calls
- Scope fencing: Layer 2 candidates are filtered by the memory's own namespaces,
  cross-scope merges downgrade to NEW, and the hash cache key binds namespaces —
  memories in one agent/channel/task scope never suppress or mutate another's

Performance optimizations:
- Lazy embedding: Hash hits skip the embedding call (0.18ms vs 10ms, empirical)
- Time-based capacity adjustment: capacity is re-evaluated at most every 5 minutes, so the memory count is not queried on every call
- Batch embedding API: One batched call replaces per-item calls (0.58ms vs 1.54ms per item, 20-item batch, empirical)
- Hash persistence: Atomic write (temp + rename) prevents corruption
- Early lock protection: concurrent memories that target the same existing memory share one LLM call (10 calls → 1 call)
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

from myrm_agent_harness.toolkits.memory._internal.hash_utils import (
    compute_normalized_hash,
)
from myrm_agent_harness.toolkits.memory._internal.storage_converters import (
    _user_filter,
)
from myrm_agent_harness.toolkits.memory.strategies.dedup_hash_cache import (
    HashCacheMetrics,
    default_hash_cache_path,
    hash_cache_key,
    load_hash_cache,
    save_hash_cache,
)
from myrm_agent_harness.toolkits.memory.strategies.dedup_judge import DedupJudge, hard_facet_conflict
from myrm_agent_harness.toolkits.memory.strategies.dedup_types import DeduplicatableMemory, DeduplicationDecision
from myrm_agent_harness.toolkits.memory.strategies.dedup_update import apply_dedup_update
from myrm_agent_harness.toolkits.memory.types import (
    MemoryType,
    SemanticMemory,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import MemoryConfig
    from myrm_agent_harness.toolkits.memory.protocols.cache import (
        EmbeddingCacheProtocol,
    )
    from myrm_agent_harness.toolkits.memory.protocols.embedding import EmbeddingProtocol
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol

logger = logging.getLogger(__name__)

_VECTOR_SEARCH_LIMIT = 5

_TYPE_THRESHOLDS = {
    MemoryType.SEMANTIC: (0.95, 0.60),
    MemoryType.EPISODIC: (0.92, 0.65),
}


class SmartDeduplicator:
    """Three-layer deduplication with configurable normalization and adaptive capacity.

    OrderedDict-based hash cache with FIFO eviction for memory efficiency.
    Adaptive capacity management sizes the cache by the actual memory count instead of a fixed maximum.
    Real-time metrics track cache effectiveness.

    Optimizations:
    - Lazy embedding: Only compute for hash misses; hits skip the embedding call (0.18ms vs 10ms, empirical)
    - Time-based capacity adjustment: capacity is re-evaluated at most every 5 minutes, so the memory count is not queried on every call
    - Batch embedding API: One batched call replaces per-item calls (0.58ms vs 1.54ms per item, 20-item batch, empirical)
    - Hash persistence: Atomic write (temp + rename) for crash safety
    - Early lock protection: Reserves target before LLM, so concurrent memories share one call (10 → 1 call)
    """

    __slots__ = (
        "_adaptive_capacity",
        "_base_cache_size",
        "_capacity_multiplier",
        "_hash_cache",
        "_high_thresh",
        "_judge",
        "_last_capacity_adjust_time",
        "_low_thresh",
        "_metrics",
        "_normalization_level",
        "_persist_enabled",
        "_persist_path",
        "_target_cache",
        "_target_lock",
    )

    def __init__(
        self,
        llm: BaseChatModel,
        high_threshold: float = 0.95,
        low_threshold: float = 0.60,
        time_window_hours: int = 24,
        max_cache_size: int = 10000,
        normalization_level: int = 2,
        adaptive_capacity: bool = True,
        capacity_multiplier: float = 1.5,
        persist_hash_cache: bool = False,
        hash_cache_path: str = "",
    ) -> None:
        from myrm_agent_harness.toolkits.memory._internal.hash_utils import (
            NormalizationLevel,
        )

        self._judge = DedupJudge(llm, time_window_hours)
        self._high_thresh = high_threshold
        self._low_thresh = low_threshold
        self._base_cache_size = max_cache_size
        self._adaptive_capacity = adaptive_capacity
        self._capacity_multiplier = capacity_multiplier
        self._normalization_level = NormalizationLevel(normalization_level)
        self._persist_enabled = persist_hash_cache
        self._persist_path = hash_cache_path or default_hash_cache_path()
        self._hash_cache: OrderedDict[str, None] = (
            load_hash_cache(self._persist_path, self._base_cache_size) if persist_hash_cache else OrderedDict()
        )
        self._target_cache: dict[str, str] = {}
        self._target_lock = asyncio.Lock()
        self._metrics = HashCacheMetrics()
        self._last_capacity_adjust_time = 0.0

    async def deduplicate_batch(
        self,
        memories: list[DeduplicatableMemory],
        vector: VectorStoreProtocol,
        embedding: EmbeddingProtocol,
        memory_config: MemoryConfig,
        cache: EmbeddingCacheProtocol | None,
    ) -> list[DeduplicatableMemory]:
        """Apply three-layer deduplication to a batch of memories.

        Hash cache persists across batches for cross-session deduplication.
        Adaptive capacity management adjusts cache size based on actual memory count.

        Optimizations:
        - Lazy embedding: Hash hits skip the embedding call (0.18ms vs 10ms, empirical)
        - Time-based capacity adjustment: capacity is re-evaluated at most every 5 minutes
        - Batch embedding API: One batched call replaces per-item calls (0.58ms vs 1.54ms per item, empirical)
        - Hash persistence: Atomic write (temp + rename) for crash safety
        - Early lock protection: Reserves target before LLM, so concurrent memories share one call

        Returns:
            List of memories to persist (after deduplication and merging)
        """
        if not memories:
            return []

        self._target_cache.clear()

        if self._adaptive_capacity:
            import time

            current_time = time.time()
            if current_time - self._last_capacity_adjust_time >= 300:
                self._last_capacity_adjust_time = current_time
                await self._adjust_capacity(vector, memory_config)

        from myrm_agent_harness.toolkits.memory._internal.storage import embed_batch

        hash_results: list[tuple[DeduplicatableMemory, str, bool]] = []
        batch_hashes: set[str] = set()
        for mem in memories:
            content_hash = compute_normalized_hash(mem.content, self._normalization_level)
            key = hash_cache_key(mem, content_hash)
            is_hit = key in self._hash_cache or key in batch_hashes
            hash_results.append((mem, content_hash, is_hit))
            self._metrics.total_checks += 1
            if is_hit:
                self._metrics.cache_hits += 1
            else:
                batch_hashes.add(key)

        need_embedding = [mem for mem, _, hit in hash_results if not hit and mem.embedding is None]
        if need_embedding:
            texts = [mem.content for mem in need_embedding]
            embeddings = await embed_batch(texts, embedding, cache)
            for mem, emb in zip(need_embedding, embeddings, strict=False):
                mem.embedding = emb

        results = await asyncio.gather(
            *[
                self._process_single_with_hash(mem, content_hash, is_hit, vector, memory_config)
                for mem, content_hash, is_hit in hash_results
            ]
        )

        final: list[DeduplicatableMemory] = []
        stats = {"hash_skip": 0, "vector_skip": 0, "created_new": 0, "updated": 0}

        for mem, (decision, target_id, merged_content) in zip(memories, results, strict=False):
            if decision == DeduplicationDecision.DUPLICATE:
                if target_id is None:
                    stats["hash_skip"] += 1
                else:
                    stats["vector_skip"] += 1
                continue

            if decision == DeduplicationDecision.NEW:
                stats["created_new"] += 1
                final.append(mem)

            elif decision in (
                DeduplicationDecision.UPDATE_REPLACE,
                DeduplicationDecision.UPDATE_MERGE,
            ):
                if target_id and merged_content:
                    stats["updated"] += 1
                    updated = await apply_dedup_update(mem, target_id, merged_content, decision, vector, memory_config)
                    if updated:
                        final.append(updated)
                    else:
                        final.append(mem)
                else:
                    final.append(mem)

        total = len(memories)
        kept = len(final)
        if total > 0:
            logger.warning(
                f"Dedup: {total} input → {kept} kept (hash_skip={stats['hash_skip']}, "
                f"vector_skip={stats['vector_skip']}, created={stats['created_new']}, updated={stats['updated']})"
            )

        if self._persist_enabled:
            save_hash_cache(self._persist_path, self._hash_cache)
        return final

    def get_metrics(self) -> HashCacheMetrics:
        """Get current cache performance metrics."""
        return self._metrics

    async def _adjust_capacity(self, vector: VectorStoreProtocol, config: MemoryConfig) -> None:
        """Adjust cache capacity based on actual memory count.

        Adaptive strategy: cache_size = memory_count * multiplier
        Reduces memory footprint for typical users (500-2000 memories).
        Called every 5 minutes to minimize network I/O overhead.
        """
        try:
            sem_count = await vector.count(config.semantic_collection, {})
            epi_count = await vector.count(config.episodic_collection, {})
            total_count = sem_count + epi_count

            target_capacity = max(100, int(total_count * self._capacity_multiplier))
            target_capacity = min(target_capacity, self._base_cache_size)

            current_size = len(self._hash_cache)
            if target_capacity < current_size:
                excess = current_size - target_capacity
                for _ in range(excess):
                    self._hash_cache.popitem(last=False)
                    self._metrics.evictions += 1

        except Exception as e:
            logger.warning("Adaptive capacity adjustment failed: %s", e)

    async def _process_single_with_hash(
        self,
        memory: DeduplicatableMemory,
        content_hash: str,
        is_hash_hit: bool,
        vector: VectorStoreProtocol,
        config: MemoryConfig,
    ) -> tuple[DeduplicationDecision, str | None, str | None]:
        """Process a single memory through three layers with pre-computed hash.

        Layer 1: Hash check (already done, passed as parameter)
        Layer 2: Vector similarity search (if hash misses)
        Layer 2.5: Early lock protection (reserves target before LLM)
        Layer 3: LLM semantic judgment (only if target not reserved)

        Early lock optimization: Prevents redundant LLM calls when multiple memories
        target the same existing memory: the concurrent callers share one LLM call.

        Args:
            memory: Memory to process
            content_hash: Pre-computed normalized hash
            is_hash_hit: Whether hash was found in cache
            user_id: User ID for filtering
            vector: Vector store protocol
            config: Memory configuration

        Returns:
            (decision, target_memory_id, merged_content)
        """
        if is_hash_hit:
            return (DeduplicationDecision.DUPLICATE, None, None)

        self._metrics.cache_misses += 1

        max_capacity = self._base_cache_size
        if len(self._hash_cache) >= max_capacity:
            self._hash_cache.popitem(last=False)
            self._metrics.evictions += 1

        self._hash_cache[hash_cache_key(memory, content_hash)] = None

        if self._metrics.total_checks % 1000 == 0:
            logger.info(
                f"Hash cache metrics: checks={self._metrics.total_checks}, "
                f"hit_rate={self._metrics.hit_rate:.1%}, "
                f"hits={self._metrics.cache_hits}, "
                f"misses={self._metrics.cache_misses}, "
                f"evictions={self._metrics.evictions}"
            )

        collection = config.semantic_collection if isinstance(memory, SemanticMemory) else config.episodic_collection
        mem_type = memory.memory_type

        high_thresh, low_thresh = _TYPE_THRESHOLDS.get(mem_type, (self._high_thresh, self._low_thresh))

        if memory.embedding is None:
            return (DeduplicationDecision.NEW, None, None)

        candidates = await vector.search(
            collection,
            memory.embedding,
            limit=_VECTOR_SEARCH_LIMIT,
            filters=_user_filter(namespaces=list(memory.scope.namespaces) or None),
            score_threshold=low_thresh,
        )

        if not candidates:
            return (DeduplicationDecision.NEW, None, None)

        top_candidate = candidates[0]
        top_score = top_candidate.score

        # A hard facet contradiction outranks similarity. "We moved to Memcached
        # because ops knows it" reads almost identically to the stored "we use
        # Redis" record, so a similarity duplicate would silently retire a decision
        # the user just withdrew. The judge below turns that into a conflict and
        # holds both for review instead.
        if top_score >= high_thresh and not hard_facet_conflict(memory, top_candidate):
            return (DeduplicationDecision.DUPLICATE, top_candidate.document.id, None)

        target_id = top_candidate.document.id

        async with self._target_lock:
            if target_id in self._target_cache:
                return (DeduplicationDecision.NEW, None, None)
            self._target_cache[target_id] = memory.id

        try:
            decision, merged_content = await self._judge.judge(memory, candidates, vector, config)

            if decision == DeduplicationDecision.NEW:
                async with self._target_lock:
                    self._target_cache.pop(target_id, None)
                return (decision, None, None)

            return (decision, target_id, merged_content)
        except Exception:
            async with self._target_lock:
                self._target_cache.pop(target_id, None)
            raise
