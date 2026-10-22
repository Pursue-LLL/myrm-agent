"""
[POS] app/services/memory/recall_simulator_service.py
[INPUT] app/schemas/memory_recall_simulator.py
[OUTPUT] RecallSimulatorService, get_recall_simulator_service
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from app.schemas.memory_recall_simulator import (
    MemoryGovernanceUpdateRequest,
    MemoryGovernanceUpdateResponse,
    RecallCandidate,
    RecallCandidateScore,
    RecallSimulateRequest,
    RecallSimulateResponse,
)


class RecallSimulatorService:
    """Service simulating multi-channel memory recall and in-place secondary governance."""

    def __init__(self) -> None:
        self._memory_store: Dict[str, RecallCandidate] = self._init_seed_memories()

    def _init_seed_memories(self) -> Dict[str, RecallCandidate]:
        """Seed a representative corpus of episodic memories, procedures, and pitfall genes."""
        seeds: List[RecallCandidate] = [
            RecallCandidate(
                memory_id="mem-linux-deadlock-01",
                content="Linux 内核模块调试中，在中断上下文 (Interrupt Context) 中严禁调用互斥锁 mutex_lock，否则必然引发睡眠调度导致内核 Panic 死锁。必须改用 spin_lock_irqsave。",
                summary="中断上下文严禁使用 mutex，必须使用自旋锁 spin_lock_irqsave 避坑",
                recall_type="causal_gene",
                scores=RecallCandidateScore(
                    rrf_score=0.94,
                    bm25_score=12.8,
                    vector_similarity=0.88,
                    causal_relevance=0.96,
                ),
                confidence=0.95,
                is_negative_trap=True,
                status="active",
                hit_reason="命中因果避坑基因【Linux 内核死锁】与中断上下文并发规则",
                tags=["Linux", "Kernel", "Deadlock", "Pitfall"],
            ),
            RecallCandidate(
                memory_id="mem-react-rerender-02",
                content="超大列表或复杂 Canvas 场景下，频繁 setState 导致父组件无谓重绘。使用 useMemo 缓存密集计算并在子组件采用 React.memo 配合 useCallback 维持函数引用稳定。",
                summary="React 密集渲染下结合 useMemo 与 React.memo 隔绝无效 Diff",
                recall_type="vector",
                scores=RecallCandidateScore(
                    rrf_score=0.86,
                    bm25_score=9.4,
                    vector_similarity=0.91,
                    causal_relevance=0.72,
                ),
                confidence=0.85,
                is_negative_trap=False,
                status="active",
                hit_reason="向量余弦相似度最高，高度匹配【前端性能优化/重绘】上下文",
                tags=["React", "Frontend", "Performance", "Optimization"],
            ),
            RecallCandidate(
                memory_id="mem-fastapi-concurrency-03",
                content="FastAPI 在定义同步阻塞 I/O（如直接请求第三方外部 API 或调用磁盘阻塞文件）时，切忌使用 async def，否则会阻塞全局单线程事件循环。需声明为普通 def 或使用 run_in_threadpool 委派。",
                summary="FastAPI 遇到同步 I/O 必须声明为普通 def 以防事件循环拥塞",
                recall_type="bm25",
                scores=RecallCandidateScore(
                    rrf_score=0.79,
                    bm25_score=14.2,
                    vector_similarity=0.76,
                    causal_relevance=0.68,
                ),
                confidence=0.90,
                is_negative_trap=True,
                status="active",
                hit_reason="BM25 词法高频匹配【FastAPI / 并发 / 事件循环】关键词",
                tags=["FastAPI", "Python", "Concurrency", "AsyncIO"],
            ),
            RecallCandidate(
                memory_id="mem-threejs-render-04",
                content="构建 3D 页面 WebGL 场景时，几何体与材质在组件销毁时必须显式调用 dispose() 释放 GPU 显存，防止单页应用路由切换累积显存泄漏崩溃。",
                summary="Three.js 场景卸载时必须手动释放 BufferGeometry 与 Material",
                recall_type="vector",
                scores=RecallCandidateScore(
                    rrf_score=0.72,
                    bm25_score=8.1,
                    vector_similarity=0.84,
                    causal_relevance=0.55,
                ),
                confidence=0.80,
                is_negative_trap=False,
                status="active",
                hit_reason="向量语义匹配【3D 页面 / ThreeJS / 渲染性能】语义簇",
                tags=["ThreeJS", "WebGL", "3D", "MemoryLeak"],
            ),
        ]
        return {item.memory_id: item for item in seeds}

    def simulate_recall(self, request: RecallSimulateRequest) -> RecallSimulateResponse:
        """Execute simulated multi-channel retrieval and RRF reranking."""
        start_time = time.perf_counter()
        query_lower = request.query.lower().strip()
        matched: List[RecallCandidate] = []

        for candidate in self._memory_store.values():
            if candidate.status == "disabled":
                continue

            if request.domain_filter:
                filter_lower = request.domain_filter.lower()
                matches_tag = any(filter_lower in t.lower() for t in candidate.tags)
                if not matches_tag:
                    continue

            # Calculate dynamic lexical and semantic relevance heuristic
            tokens = [w for w in query_lower.split() if len(w) > 1]
            token_hits = sum(1 for w in tokens if w in candidate.content.lower() or w in candidate.summary.lower())
            lexical_boost = min(token_hits * 1.5, 5.0)

            updated_scores = RecallCandidateScore(
                rrf_score=min(candidate.scores.rrf_score + (0.02 * lexical_boost), 0.99),
                bm25_score=candidate.scores.bm25_score + lexical_boost,
                vector_similarity=candidate.scores.vector_similarity,
                causal_relevance=candidate.scores.causal_relevance,
            )

            matched.append(
                RecallCandidate(
                    memory_id=candidate.memory_id,
                    content=candidate.content,
                    summary=candidate.summary,
                    recall_type=candidate.recall_type,
                    scores=updated_scores,
                    confidence=candidate.confidence,
                    is_negative_trap=candidate.is_negative_trap,
                    status=candidate.status,
                    hit_reason=candidate.hit_reason,
                    tags=candidate.tags,
                )
            )

        # Sort candidates descending by weighted RRF score and operator confidence
        matched.sort(
            key=lambda item: item.scores.rrf_score * item.confidence,
            reverse=True,
        )

        top_candidates = matched[: request.top_k]
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return RecallSimulateResponse(
            query=request.query,
            total_matched=len(matched),
            candidates=top_candidates,
            execution_latency_ms=max(latency_ms, 1.2),
        )

    def update_governance(self, request: MemoryGovernanceUpdateRequest) -> MemoryGovernanceUpdateResponse:
        """Perform secondary governance modification on an existing memory candidate."""
        target = self._memory_store.get(request.memory_id)
        if not target:
            # Create a lightweight ad-hoc memory item if not previously present
            target = RecallCandidate(
                memory_id=request.memory_id,
                content=f"动态注册的经验项 {request.memory_id}",
                summary="动态注册经验摘要",
                recall_type="vector",
                scores=RecallCandidateScore(
                    rrf_score=0.75,
                    bm25_score=8.0,
                    vector_similarity=0.75,
                    causal_relevance=0.60,
                ),
                confidence=0.8,
                is_negative_trap=False,
                status="active",
                hit_reason="手动注册或治理的新增记忆条目",
                tags=["Custom"],
            )
            self._memory_store[request.memory_id] = target

        # Handle merging duplicate memory
        if request.merged_into_id and request.merged_into_id in self._memory_store:
            parent = self._memory_store[request.merged_into_id]
            merged_tags = list(set(parent.tags + target.tags))
            updated_parent = RecallCandidate(
                memory_id=parent.memory_id,
                content=f"{parent.content}\n[合并附加]: {target.content}",
                summary=parent.summary,
                recall_type=parent.recall_type,
                scores=parent.scores,
                confidence=parent.confidence,
                is_negative_trap=parent.is_negative_trap,
                status=parent.status,
                hit_reason=f"{parent.hit_reason} (已合并 {target.memory_id})",
                tags=merged_tags,
            )
            self._memory_store[parent.memory_id] = updated_parent
            target.status = "disabled"

        new_confidence = request.confidence if request.confidence is not None else target.confidence
        new_is_negative_trap = request.is_negative_trap if request.is_negative_trap is not None else target.is_negative_trap
        new_status = request.status if request.status is not None else target.status

        updated_record = RecallCandidate(
            memory_id=target.memory_id,
            content=target.content,
            summary=target.summary,
            recall_type=target.recall_type,
            scores=target.scores,
            confidence=new_confidence,
            is_negative_trap=new_is_negative_trap,
            status=new_status,
            hit_reason=target.hit_reason,
            tags=target.tags,
        )

        self._memory_store[target.memory_id] = updated_record

        return MemoryGovernanceUpdateResponse(
            success=True,
            memory_id=target.memory_id,
            message="Memory secondary governance parameters updated successfully",
            updated_record=updated_record,
        )


_instance: Optional[RecallSimulatorService] = None


def get_recall_simulator_service() -> RecallSimulatorService:
    """Dependency provider yielding singleton RecallSimulatorService instance."""
    global _instance
    if _instance is None:
        _instance = RecallSimulatorService()
    return _instance
