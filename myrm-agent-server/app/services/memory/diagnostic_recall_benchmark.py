"""Golden recall benchmark probe for Memory Doctor.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: protocol-first memory runtime)

[OUTPUT]
run_golden_recall_benchmark: content-safe probe result with structured MemoryCommandBenchmarkSummary for semantic/episodic recall quality.

[POS]
单用户记忆召回基准探针。临时写入合成记忆、检索、再清理，只输出计数/排名证据，不暴露用户业务记忆内容。
Covers 8 categories: architecture_decision, workflow_event, user_preference, temporal_reasoning,
cjk_retrieval, multi_session, knowledge_update, procedural_skill.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from myrm_agent_harness.toolkits.memory import (
    EpisodicMemory,
    MemoryManager,
    MemoryRecallBenchmarkCase,
    MemoryRecallBenchmarkResult,
    MemoryType,
    SemanticMemory,
    summarize_recall_benchmark,
)

from app.schemas.memory.command_center import MemoryCommandBenchmarkSummary, MemoryCommandDiagnosticProbeResult
from app.services.memory.diagnostic_probe_results import critical_probe, missing_probe
from app.services.memory.diagnostic_repair_plans import with_probe_repair_plans

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _BenchmarkPair:
    """A synthetic memory + its retrieval query for one benchmark case."""

    case_id: str
    category: str
    content: str
    query: str
    memory_type: MemoryType
    language: str = "en"


_BENCHMARK_PAIRS: list[_BenchmarkPair] = [
    _BenchmarkPair(
        case_id="arch_decision_en",
        category="architecture_decision",
        content="diagnostic benchmark {run_id} architecture decision: chose PostgreSQL for billing data integrity over MongoDB",
        query="architecture decision recall PostgreSQL billing {run_id}",
        memory_type=MemoryType.SEMANTIC,
    ),
    _BenchmarkPair(
        case_id="arch_decision_zh",
        category="architecture_decision",
        content="diagnostic benchmark {run_id} 架构决策：选择 Redis 做会话缓存因为 Memcached 不支持持久化",
        query="架构决策 会话缓存 Redis {run_id}",
        memory_type=MemoryType.SEMANTIC,
        language="zh",
    ),
    _BenchmarkPair(
        case_id="workflow_event_en",
        category="workflow_event",
        content="diagnostic benchmark {run_id} workflow event: fixed login redirect bug caused by missing trailing slash",
        query="workflow event login redirect bug fix {run_id}",
        memory_type=MemoryType.EPISODIC,
    ),
    _BenchmarkPair(
        case_id="workflow_event_zh",
        category="workflow_event",
        content="diagnostic benchmark {run_id} 工作流事件：修复文件上传超时问题 Nginx client_max_body_size",
        query="工作流事件 文件上传超时 {run_id}",
        memory_type=MemoryType.EPISODIC,
        language="zh",
    ),
    _BenchmarkPair(
        case_id="user_pref_en",
        category="user_preference",
        content="diagnostic benchmark {run_id} user preference: prefers Python with type hints, dislikes verbose boilerplate",
        query="user preference programming language Python type hints {run_id}",
        memory_type=MemoryType.SEMANTIC,
    ),
    _BenchmarkPair(
        case_id="user_pref_zh",
        category="user_preference",
        content="diagnostic benchmark {run_id} 用户偏好：偏好 Tailwind CSS 而非 Bootstrap 认为 utility-first 灵活",
        query="用户偏好 CSS 框架 Tailwind {run_id}",
        memory_type=MemoryType.SEMANTIC,
        language="zh",
    ),
    _BenchmarkPair(
        case_id="temporal_en",
        category="temporal_reasoning",
        content="diagnostic benchmark {run_id} temporal: last Monday CI pipeline down 3 hours Docker Hub rate limit switched to GHCR",
        query="when CI pipeline down Docker Hub rate limit {run_id}",
        memory_type=MemoryType.EPISODIC,
    ),
    _BenchmarkPair(
        case_id="temporal_zh",
        category="temporal_reasoning",
        content="diagnostic benchmark {run_id} 时间事件：上周五部署 Grafana Prometheus 监控系统替代 Datadog",
        query="上周五 部署 监控系统 Grafana {run_id}",
        memory_type=MemoryType.EPISODIC,
        language="zh",
    ),
    _BenchmarkPair(
        case_id="cjk_01",
        category="cjk_retrieval",
        content="diagnostic benchmark {run_id} 中文检索：微服务架构 gRPC 服务间通信 消息队列 RabbitMQ",
        query="微服务 服务间通信 消息队列 {run_id}",
        memory_type=MemoryType.SEMANTIC,
        language="zh",
    ),
    _BenchmarkPair(
        case_id="cjk_02",
        category="cjk_retrieval",
        content="diagnostic benchmark {run_id} 中文检索：数据库分库分表 按用户ID取模 8个分片 PostgreSQL",
        query="数据库 分库分表 分片策略 {run_id}",
        memory_type=MemoryType.SEMANTIC,
        language="zh",
    ),
    _BenchmarkPair(
        case_id="multi_session_en",
        category="multi_session",
        content="diagnostic benchmark {run_id} multi-session: API rate limiting evolved from fixed window to sliding window counters in Redis",
        query="API rate limiting strategy evolution sliding window {run_id}",
        memory_type=MemoryType.SEMANTIC,
    ),
    _BenchmarkPair(
        case_id="multi_session_zh",
        category="multi_session",
        content="diagnostic benchmark {run_id} 多轮会话：权限模型从 RBAC 演变为 ABAC 混合模式支持租户级细粒度控制",
        query="权限模型 RBAC ABAC 演变 {run_id}",
        memory_type=MemoryType.SEMANTIC,
        language="zh",
    ),
    _BenchmarkPair(
        case_id="knowledge_update_en",
        category="knowledge_update",
        content="diagnostic benchmark {run_id} knowledge update: switched mobile API from REST to GraphQL, REST decision deprecated",
        query="mobile API GraphQL REST deprecated update {run_id}",
        memory_type=MemoryType.SEMANTIC,
    ),
    _BenchmarkPair(
        case_id="knowledge_update_zh",
        category="knowledge_update",
        content="diagnostic benchmark {run_id} 知识更新：前端框架从 Vue 2 迁移到 Vue 3 完成，Vue 2 偏好已过时",
        query="前端框架 Vue 迁移更新 {run_id}",
        memory_type=MemoryType.SEMANTIC,
        language="zh",
    ),
    _BenchmarkPair(
        case_id="procedural_en",
        category="procedural_skill",
        content="diagnostic benchmark {run_id} procedural: production deployment must run database migrations before application code",
        query="production deployment order database migrations {run_id}",
        memory_type=MemoryType.SEMANTIC,
    ),
    _BenchmarkPair(
        case_id="procedural_zh",
        category="procedural_skill",
        content="diagnostic benchmark {run_id} 操作步骤：调试内存泄漏先 memory_profiler 基线再 objgraph 追踪引用链",
        query="调试内存泄漏 步骤 memory_profiler {run_id}",
        memory_type=MemoryType.SEMANTIC,
        language="zh",
    ),
]


async def run_golden_recall_benchmark(manager: MemoryManager | None, *, run_id: str) -> MemoryCommandDiagnosticProbeResult:
    """Run a synthetic top-k recall benchmark across 8 categories and remove probe memories."""

    started = perf_counter()
    if manager is None or not manager.has_vector:
        return with_probe_repair_plans(
            missing_probe(
                probe_id="golden_recall_benchmark",
                category="index",
                label="Golden recall benchmark",
                started=started,
                evidence="Vector-backed memory search is unavailable, so golden recall benchmark was skipped.",
                impact="Real recall quality cannot be measured until semantic indexing is available.",
                next_action="Enable vector-backed memory search and rerun diagnostics.",
            )
        )

    stored_memories: list[tuple[_BenchmarkPair, SemanticMemory | EpisodicMemory]] = []
    try:
        for pair in _BENCHMARK_PAIRS:
            content = pair.content.replace("{run_id}", run_id)
            if pair.memory_type == MemoryType.SEMANTIC:
                mem = SemanticMemory(
                    content=content,
                    importance=0.9,
                    tags=["diagnostic_benchmark"],
                    metadata={"diagnostic_probe": True, "diagnostic_run_id": run_id, "category": pair.category},
                    language=pair.language,
                )
            else:
                mem = EpisodicMemory(
                    content=content,
                    event_type="diagnostic_benchmark",
                    related_entities=["memory_doctor"],
                    importance=0.9,
                    metadata={"diagnostic_probe": True, "diagnostic_run_id": run_id, "category": pair.category},
                    language=pair.language,
                )
            result = await manager.store(mem, _bypass_approval=True)
            if isinstance(result, (SemanticMemory, EpisodicMemory)):
                stored_memories.append((pair, result))

        if len(stored_memories) < len(_BENCHMARK_PAIRS):
            probe = critical_probe(
                probe_id="golden_recall_benchmark",
                category="index",
                label="Golden recall benchmark",
                started=started,
                evidence=f"Only {len(stored_memories)}/{len(_BENCHMARK_PAIRS)} benchmark memories stored.",
                impact="Partial recall quality measurement due to incomplete benchmark setup.",
                next_action="Review memory write routing and rerun diagnostics.",
                repair_actions=["review_storage_config", "run_diagnostics"],
            )
        else:
            benchmark_results: list[MemoryRecallBenchmarkResult] = []
            for pair, stored_mem in stored_memories:
                query = pair.query.replace("{run_id}", run_id)
                case_result = await _run_case(
                    manager,
                    MemoryRecallBenchmarkCase(
                        id=pair.case_id,
                        query=query,
                        expected_memory_ids=[stored_mem.id],
                        top_k=5,
                    ),
                    memory_type=pair.memory_type,
                    category=pair.category,
                )
                benchmark_results.append(case_result)

            summary = summarize_recall_benchmark(benchmark_results)
            categories_hit = _count_category_hits(benchmark_results)
            categories_dict = _build_categories_dict(benchmark_results)
            evidence = (
                f"Golden recall benchmark: {summary.passed_count}/{summary.case_count} cases passed; "
                f"recall@5={summary.recall_at_k:.2f}, ndcg@5={summary.ndcg_at_k:.2f}, "
                f"mrr={summary.mrr_score:.2f}, precision@5={summary.precision_at_k:.2f}, "
                f"latency_p50={summary.latency_p50_ms:.0f}ms, latency_p95={summary.latency_p95_ms:.0f}ms. "
                f"Categories: {categories_hit}."
            )
            probe = MemoryCommandDiagnosticProbeResult(
                id="golden_recall_benchmark",
                category="index",
                label="Golden recall benchmark",
                status=summary.status,
                evidence=evidence,
                impact="Synthetic recall checks verify that memory write-then-retrieve works across 8 categories and 2 languages.",
                next_action="No action required."
                if summary.status == "ready"
                else "Review retrieval trace, vector index, and embedding configuration, then rerun diagnostics.",
                safe_to_retry=True,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                benchmark_summary=MemoryCommandBenchmarkSummary(
                    case_count=summary.case_count,
                    passed_count=summary.passed_count,
                    recall_at_k=summary.recall_at_k,
                    ndcg_at_k=summary.ndcg_at_k,
                    mrr_score=summary.mrr_score,
                    precision_at_k=summary.precision_at_k,
                    latency_p50_ms=summary.latency_p50_ms,
                    latency_p95_ms=summary.latency_p95_ms,
                    top_k=5,
                    categories=categories_dict,
                ),
                repair_actions=[] if summary.status == "ready" else ["review_retrieval_trace", "run_diagnostics"],
            )
    except Exception as exc:
        probe = critical_probe(
            probe_id="golden_recall_benchmark",
            category="index",
            label="Golden recall benchmark",
            started=started,
            evidence=f"Golden recall benchmark failed: {type(exc).__name__}.",
            impact="Recall quality cannot be proven for newly written memories in this runtime.",
            next_action="Review storage, embedding, and vector index configuration, then rerun diagnostics.",
            repair_actions=["review_storage_config", "configure_embedding", "run_diagnostics"],
        )

    cleanup_errors = await _cleanup_stored_memories(manager, stored_memories)
    if cleanup_errors:
        repair_actions = list(dict.fromkeys([*probe.repair_actions, "review_storage_config"]))
        probe = probe.model_copy(
            update={
                "status": "warning" if probe.status == "ready" else probe.status,
                "evidence": f"{probe.evidence} cleanup_failures={cleanup_errors}.",
                "next_action": "Review local vector storage cleanup before trusting repeated benchmark runs.",
                "repair_actions": repair_actions,
            }
        )
    return with_probe_repair_plans(probe)


def _count_category_hits(results: list[MemoryRecallBenchmarkResult]) -> str:
    """Summarize per-category pass/total for evidence string."""
    cat_stats = _aggregate_category_stats(results)
    parts: list[str] = []
    for cat, hits in sorted(cat_stats.items()):
        parts.append(f"{cat}={sum(hits)}/{len(hits)}")
    return ", ".join(parts)


def _build_categories_dict(results: list[MemoryRecallBenchmarkResult]) -> dict[str, str]:
    """Build structured per-category pass/total dict for frontend rendering."""
    cat_stats = _aggregate_category_stats(results)
    return {cat: f"{sum(hits)}/{len(hits)}" for cat, hits in sorted(cat_stats.items())}


def _aggregate_category_stats(results: list[MemoryRecallBenchmarkResult]) -> dict[str, list[bool]]:
    """Aggregate per-category pass/fail stats from benchmark results."""
    from collections import defaultdict

    cat_stats: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        cat_stats[r.category or r.case_id].append(r.expected_found)
    return cat_stats


async def _run_case(
    manager: MemoryManager,
    case: MemoryRecallBenchmarkCase,
    *,
    memory_type: MemoryType,
    category: str = "",
) -> MemoryRecallBenchmarkResult:
    t0 = perf_counter()
    results = await manager.search(case.query, memory_types=[memory_type], limit=case.top_k, use_rrf=True)
    latency_ms = round((perf_counter() - t0) * 1000, 2)
    hit_ids = [result.id for result in results]
    matching_ranks = [idx + 1 for idx, memory_id in enumerate(hit_ids) if memory_id in case.expected_memory_ids]
    best_rank = min(matching_ranks) if matching_ranks else None
    score = 1.0 / best_rank if best_rank else 0.0
    return MemoryRecallBenchmarkResult(
        case_id=case.id,
        category=category,
        expected_found=best_rank is not None,
        best_rank=best_rank,
        top_k=case.top_k,
        hit_count=len(results),
        score=round(score, 4),
        latency_ms=latency_ms,
        evidence=f"case={case.id}; hit_count={len(results)}; best_rank={best_rank or 0}; latency={latency_ms}ms.",
    )


async def _cleanup_stored_memories(
    manager: MemoryManager,
    stored_memories: list[tuple[_BenchmarkPair, SemanticMemory | EpisodicMemory]],
) -> int:
    """Delete all stored benchmark memories. Returns count of cleanup errors."""
    error_count = 0
    for pair, mem in stored_memories:
        try:
            collection = (
                manager.config.semantic_collection
                if pair.memory_type == MemoryType.SEMANTIC
                else manager.config.episodic_collection
            )
            await manager.delete_memory(collection, [mem.id])
        except Exception as exc:
            logger.warning("Golden recall cleanup failed for %s: %s", pair.case_id, exc)
            error_count += 1
    return error_count
