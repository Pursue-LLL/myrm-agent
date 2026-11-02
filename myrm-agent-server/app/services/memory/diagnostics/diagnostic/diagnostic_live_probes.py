"""Live Memory Doctor probes.

[INPUT]
app.services.memory.shared_context.shared_context_health::check_shared_context_memory_health (POS: Shared Context 记忆健康服务)
myrm_agent_harness.toolkits.memory::MemoryManager (POS: 记忆管理器)

[OUTPUT]
run_embedding_live_probe: real embedding request, graded ready/missing/critical.
run_retrieval_pipeline_probe: content-safe search that proves fusion and trace capture.
run_sparse_cjk_recall_probe: CJK keyword query that proves the BM25/RRF sparse path.

[POS]
单用户记忆诊断的运行期探针。每个探针对真实依赖发起一次不暴露业务内容的请求，检索类探针以 `track_access=False` 发起，探针命中的记忆不会被记为「最近使用」。
"""

from __future__ import annotations

from time import perf_counter

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType

from app.schemas.memory.command_center import MemoryCommandDiagnosticProbeResult
from app.services.memory.shared_context.shared_context_health import (
    EMBEDDING_NOT_CONFIGURED_REASON,
    check_shared_context_memory_health,
)

from .diagnostic_probe_results import (
    KEYWORD_MODE_EVIDENCE,
    KEYWORD_MODE_IMPACT,
    KEYWORD_MODE_NEXT_ACTION,
    DiagnosticStatus,
    critical_probe,
    missing_probe,
)


async def run_embedding_live_probe() -> MemoryCommandDiagnosticProbeResult:
    started = perf_counter()
    result = await check_shared_context_memory_health(probe=True)
    impact = "Semantic and episodic memories cannot be reliably indexed or recalled if live embeddings fail."
    next_action = "Configure a working embedding provider and rerun diagnostics."
    if result.ready:
        status: DiagnosticStatus = "ready"
        evidence = f"Embedding live probe succeeded for model {result.model}; dimension={result.vector_dimension}."
        next_action = "No action required."
        repair_actions: list[str] = []
    elif result.reason == EMBEDDING_NOT_CONFIGURED_REASON:
        status = "missing"
        evidence = KEYWORD_MODE_EVIDENCE
        impact = KEYWORD_MODE_IMPACT
        next_action = KEYWORD_MODE_NEXT_ACTION
        repair_actions = ["configure_embedding"]
    elif result.status == "not_configured":
        status = "critical"
        evidence = f"Embedding live probe was not configured: {result.reason}."
        repair_actions = ["configure_embedding"]
    else:
        status = "critical"
        evidence = f"Embedding live probe failed: {result.reason}."
        repair_actions = ["configure_embedding", "run_diagnostics"]
    return MemoryCommandDiagnosticProbeResult(
        id="embedding_live",
        category="embedding",
        label="Embedding live probe",
        status=status,
        evidence=evidence,
        impact=impact,
        next_action=next_action,
        safe_to_retry=result.retryable,
        duration_ms=round((perf_counter() - started) * 1000, 2),
        repair_actions=repair_actions,
    )


async def run_retrieval_pipeline_probe(manager: MemoryManager | None) -> MemoryCommandDiagnosticProbeResult:
    started = perf_counter()
    if manager is None:
        return missing_probe(
            probe_id="retrieval_pipeline",
            category="index",
            label="Retrieval pipeline",
            started=started,
            evidence="Memory manager dependency was not available to diagnostics.",
            impact="Search, RRF fusion, trace capture, and graph enrichment cannot be proven from this run.",
            next_action="Open the memory command center through the normal GUI runtime and rerun diagnostics.",
        )
    if not manager.get_enabled_types():
        return missing_probe(
            probe_id="retrieval_pipeline",
            category="index",
            label="Retrieval pipeline",
            started=started,
            evidence="No enabled memory types are available for retrieval.",
            impact="The agent has no searchable persistent memory backends in this runtime.",
            next_action="Enable relational or vector memory storage, then rerun diagnostics.",
        )
    try:
        results = await manager.search("memory reliability retrieval probe 记忆诊断", limit=1, track_access=False)
        trace = manager.last_retrieval_trace
    except Exception as exc:
        return critical_probe(
            probe_id="retrieval_pipeline",
            category="index",
            label="Retrieval pipeline",
            started=started,
            evidence=f"Retrieval pipeline probe failed: {exc}",
            impact="Cross-session recall and memory injection may fail during normal agent work.",
            next_action="Review embedding, vector, and relational storage configuration, then rerun diagnostics.",
            repair_actions=["review_storage_config", "configure_embedding"],
        )
    trace_steps = len(trace.steps) if trace is not None else 0
    degraded = bool(trace.degraded) if trace is not None else False
    status: DiagnosticStatus = "ready" if trace_steps and not degraded else "warning"
    evidence = f"Search completed with {len(results)} result(s); retrieval trace steps={trace_steps}."
    if degraded:
        evidence += " Retrieval was degraded (wall-clock timeout or backing-store error)."
    return MemoryCommandDiagnosticProbeResult(
        id="retrieval_pipeline",
        category="index",
        label="Retrieval pipeline",
        status=status,
        evidence=evidence,
        impact="The recall path can execute without exposing retrieved memory content in diagnostic evidence.",
        next_action="No action required." if status == "ready" else "Inspect retrieval trace capture and rerun diagnostics.",
        safe_to_retry=True,
        duration_ms=round((perf_counter() - started) * 1000, 2),
        repair_actions=[] if status == "ready" else ["run_diagnostics"],
    )


async def run_sparse_cjk_recall_probe(manager: MemoryManager | None) -> MemoryCommandDiagnosticProbeResult:
    started = perf_counter()
    if manager is None or not manager.has_vector:
        return missing_probe(
            probe_id="sparse_cjk_recall",
            category="index",
            label="Sparse CJK recall",
            started=started,
            evidence="Vector-backed memory search is unavailable, so BM25/RRF sparse recall was not executed.",
            impact="Exact keyword recall and CJK query coverage cannot be proven in this runtime.",
            next_action="Enable vector-backed memory search and rerun diagnostics.",
        )
    try:
        await manager.search(
            "记忆诊断 precise keyword BM25 CJK",
            memory_types=[MemoryType.SEMANTIC, MemoryType.EPISODIC],
            limit=1,
            use_rrf=True,
            track_access=False,
        )
    except Exception as exc:
        return critical_probe(
            probe_id="sparse_cjk_recall",
            category="index",
            label="Sparse CJK recall",
            started=started,
            evidence=f"Sparse CJK recall probe failed: {exc}",
            impact="Hybrid keyword + semantic recall may miss exact file names, identifiers, and Chinese/Japanese/Korean queries.",
            next_action="Review vector store and BM25 dependencies, then rerun diagnostics.",
            repair_actions=["enable_vector_store", "run_diagnostics"],
        )
    config = manager.config
    return MemoryCommandDiagnosticProbeResult(
        id="sparse_cjk_recall",
        category="index",
        label="Sparse CJK recall",
        status="ready",
        evidence=f"Hybrid retrieval accepted a CJK keyword query with RRF enabled; bm25_top_k={config.bm25_top_k}, max_corpus={config.bm25_max_corpus_size}.",
        impact="Exact keyword recall is available as a complement to semantic vector search.",
        next_action="No action required.",
        safe_to_retry=True,
        duration_ms=round((perf_counter() - started) * 1000, 2),
        repair_actions=[],
    )
