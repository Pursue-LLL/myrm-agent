"""Scale recall benchmark for the pure-SQLite procedural memory channel.

Covers the regression-gate scenario the golden benchmark cannot see: recall
quality and tail latency when the store grows far beyond the golden case
count. Ingestion and retrieval both run on the real product path —
``MemoryManager.store_batch`` and ``MemoryManager.search`` with the SQLite
relational backend and the vector/graph/embedding channels disabled (the
exact channel combination a no-Qdrant local deployment runs).

Deterministic corpus: anchored key rules carrying unique tokens plus
same-prefix noise rules (no random source — the corpus is identical on
every run), so expected memory ids are known upfront and the benchmark is
fully reproducible without any LLM call.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import pytest
from myrm_agent_harness.toolkits.memory import MemoryConfig, MemoryManager
from myrm_agent_harness.toolkits.memory.relational.sqlite_store import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.reliability import (
    MemoryRecallBenchmarkResult,
    summarize_recall_benchmark,
)
from myrm_agent_harness.toolkits.memory.types import MemoryType, ProceduralMemory

# CI smoke tier: finishes well under the 10-minute single-test budget on a
# developer laptop while still exercising a multi-thousand-rule corpus.
_CI_KEY_RULES = 60
_CI_NOISE_RULES = 3000
_INGEST_BATCH = 500

# Anchor token: unique per key rule, shared prefix with noise rules so the
# corpus contains near-miss distractors — not trivially separable clutter.
_ANCHOR_PREFIX = "SCALEBENCH"


@dataclass(slots=True)
class _ScaleBenchCase:
    """One anchored rule plus the query that must retrieve it."""

    anchor_token: str
    trigger: str
    query: str


def _build_key_cases(count: int) -> list[_ScaleBenchCase]:
    """Deterministic bilingual key rules; expected ids derive from anchors."""
    cases: list[_ScaleBenchCase] = []
    for i in range(count):
        token = f"{_ANCHOR_PREFIX}-KEY{i:04d}"
        trigger = f"{token} 部署约束 deployment constraint {i}"
        cases.append(
            _ScaleBenchCase(
                anchor_token=token,
                trigger=trigger,
                query=token,
            )
        )
    return cases


def _build_noise_rules(count: int) -> list[ProceduralMemory]:
    """Near-miss noise rules sharing the anchor prefix but not the tokens."""
    rules: list[ProceduralMemory] = []
    for i in range(count):
        token = f"{_ANCHOR_PREFIX}-NOISE{i:06d}"
        rules.append(
            ProceduralMemory(
                content=f"{token} 近似干扰规则 noise rule {i}",
                trigger=f"{token} 干扰 trigger {i}",
                action=f"noise action {i}",
                language="zh",
            )
        )
    return rules


async def _ingest(manager: MemoryManager, memories: list[ProceduralMemory]) -> None:
    """Bulk-ingest through the real write path in bounded batches."""
    for start in range(0, len(memories), _INGEST_BATCH):
        batch = memories[start : start + _INGEST_BATCH]
        stored = await manager.store_batch(batch, _bypass_approval=True)
        assert len(stored) == len(batch), "scale ingest batch lost rules"


async def _run_case(
    manager: MemoryManager,
    case: _ScaleBenchCase,
    expected_id: str,
) -> MemoryRecallBenchmarkResult:
    """One timed retrieval per case using the real search path (no mocks)."""
    t0 = perf_counter()
    hits = await manager.search(
        case.query,
        memory_types=[MemoryType.PROCEDURAL],
        limit=5,
        use_rrf=True,
    )
    latency_ms = (perf_counter() - t0) * 1000.0
    hit_ids = [hit.id for hit in hits]
    matching = [idx + 1 for idx, mid in enumerate(hit_ids) if mid == expected_id]
    best_rank = matching[0] if matching else None
    return MemoryRecallBenchmarkResult(
        case_id=case.anchor_token,
        expected_found=best_rank is not None,
        best_rank=best_rank,
        effective_rank=best_rank,
        top_k=5,
        hit_count=len(hits),
        score=round(1.0 / best_rank, 4) if best_rank else 0.0,
        latency_ms=round(latency_ms, 2),
        evidence=f"anchor={case.anchor_token}; rank={best_rank or 0}; latency={latency_ms:.2f}ms",
    )


@pytest.fixture
async def scale_engine(tmp_path):
    """Pure-SQLite MemoryManager on an isolated tmp database (zero product data)."""
    relational = SQLiteRelationalStore(str(tmp_path / "scale_bench.db"))
    manager = MemoryManager(
        config=MemoryConfig(
            embedding_model="scale-bench",
            collection_prefix="scale_bench",
            bm25_top_k=50,
            bm25_max_corpus_size=5000,
        ),
        user_id="scale_bench",
        relational=relational,
        vector=None,
        graph=None,
        embedding=None,
        cache=None,
    )
    yield manager
    await relational.close()


@pytest.mark.asyncio
async def test_scale_recall_and_tail_latency(scale_engine: MemoryManager) -> None:
    """Regression gate: anchored recall stays high with p99 tail visible at scale."""
    key_cases = _build_key_cases(_CI_KEY_RULES)
    noise_rules = _build_noise_rules(_CI_NOISE_RULES)

    key_memories = [
        ProceduralMemory(
            content=f"{case.anchor_token} 锚点规则 anchor rule",
            trigger=case.trigger,
            action=f"{case.anchor_token} enforce deployment constraint",
            language="zh",
        )
        for case in key_cases
    ]
    await _ingest(scale_engine, key_memories + noise_rules)

    expected_ids = {case.anchor_token: mem.id for case, mem in zip(key_cases, key_memories, strict=True)}

    # Warm-up pass: prime SQLite page cache so the timed pass is not skewed
    # by cold-start disk reads.
    for case in key_cases:
        await scale_engine.search(
            case.query,
            memory_types=[MemoryType.PROCEDURAL],
            limit=5,
            use_rrf=True,
        )

    results = [
        await _run_case(scale_engine, case, expected_ids[case.anchor_token])
        for case in key_cases
    ]
    summary = summarize_recall_benchmark(results)

    assert summary.case_count == _CI_KEY_RULES
    # Unique anchor tokens must survive a multi-thousand-rule corpus via the
    # LIKE channel: a drop here is a genuine retrieval regression.
    assert summary.recall_at_k >= 0.98, (
        f"anchored recall regressed: recall@5={summary.recall_at_k:.3f}"
    )
    assert summary.latency_p99_ms > 0.0, "tail latency must be measurable at scale"
    # CI-tier guardrail: procedural LIKE retrieval must stay in the
    # sub-second range even on developer laptops.
    assert summary.latency_p99_ms < 1000.0, (
        f"p99 tail latency breached guardrail: {summary.latency_p99_ms:.1f}ms"
    )


@pytest.mark.asyncio
async def test_scale_cjk_recall_via_real_trigger_channel(scale_engine: MemoryManager) -> None:
    """CJK queries hit the real LIKE channel through trigger text, not content."""
    trigger_text = "团队发布流程需要二次审批 release approval"
    rule = ProceduralMemory(
        content="发布流程规则说明",
        trigger=trigger_text,
        action="执行二次审批后才能发布",
        language="zh",
    )
    await _ingest(scale_engine, _build_noise_rules(200) + [rule])

    hits = await scale_engine.search(
        "团队发布流程",
        memory_types=[MemoryType.PROCEDURAL],
        limit=5,
        use_rrf=True,
    )
    assert any(hit.id == rule.id for hit in hits), (
        "CJK trigger substring failed to retrieve the anchored rule"
    )
