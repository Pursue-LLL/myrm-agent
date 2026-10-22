"""
[INPUT]
- fastapi::{APIRouter, HTTPException, status}
- pydantic::{BaseModel, Field}
- myrm_agent_harness.observability.context_retrieval::{
    PruningReason,
    RetrievalTreeNode,
    VisitedPathTrace,
    ContextRetrievalTracer,
  }

[OUTPUT]
- router: APIRouter for context retrieval traces and openviking-style simulation
- RetrievalTreeNodeDTO, VisitedPathTraceDTO, RetrievalSimulateRequest

[POS]
app/api/system/retrieval_trace_api.py — 上下文检索决策树与剪枝留痕 HTTP 端点与实验场模拟。
"""

from __future__ import annotations

import time
from typing import Dict, List

from fastapi import APIRouter, status
from myrm_agent_harness.observability.context_retrieval import (
    ContextRetrievalTracer,
    PruningReason,
    RetrievalTreeNode,
    VisitedPathTrace,
)
from pydantic import BaseModel, Field

router = APIRouter(tags=["system-retrieval-trace"])


class RetrievalTreeNodeDTO(BaseModel):
    """检索决策树节点数据传输对象。"""

    node_id: str
    name: str
    path: str
    depth: int = 0
    similarity_score: float
    pruning_threshold: float
    is_pruned: bool = False
    pruning_reason: str = PruningReason.NONE.value
    reason_detail: str = ""
    is_hit: bool = False
    metadata: Dict[str, str] = Field(default_factory=dict)
    children: List[RetrievalTreeNodeDTO] = Field(default_factory=list)


class VisitedPathTraceDTO(BaseModel):
    """上下文检索全景轨迹传输对象。"""

    trace_id: str
    query: str
    root_nodes: List[RetrievalTreeNodeDTO] = Field(default_factory=list)
    total_nodes_visited: int
    pruned_nodes_count: int
    hits_count: int
    duration_ms: float
    created_at: float


class RetrievalSimulateRequest(BaseModel):
    """检索实验场模拟请求参数。"""

    query: str = Field(..., min_length=1, description="检索查询词")
    pruning_threshold: float = Field(0.70, ge=0.0, le=1.0, description="剪枝相似度判定阈值")
    top_k: int = Field(3, ge=1, le=20, description="最大召回 Top-K 限制")


def _node_to_dto(node: RetrievalTreeNode) -> RetrievalTreeNodeDTO:
    """递归将 Harness 层 RetrievalTreeNode 转换为 DTO。"""
    return RetrievalTreeNodeDTO(
        node_id=node.node_id,
        name=node.name,
        path=node.path,
        depth=node.depth,
        similarity_score=node.similarity_score,
        pruning_threshold=node.pruning_threshold,
        is_pruned=node.is_pruned,
        pruning_reason=node.pruning_reason.value,
        reason_detail=node.reason_detail,
        is_hit=node.is_hit,
        metadata=dict(node.metadata),
        children=[_node_to_dto(child) for child in node.children],
    )


def _trace_to_dto(trace: VisitedPathTrace) -> VisitedPathTraceDTO:
    """将 Harness 层 VisitedPathTrace 转换为 DTO。"""
    return VisitedPathTraceDTO(
        trace_id=trace.trace_id,
        query=trace.query,
        root_nodes=[_node_to_dto(node) for node in trace.root_nodes],
        total_nodes_visited=trace.total_nodes_visited,
        pruned_nodes_count=trace.pruned_nodes_count,
        hits_count=trace.hits_count,
        duration_ms=trace.duration_ms,
        created_at=trace.created_at,
    )


def _build_simulation_trace(
    trace_id: str,
    query: str,
    threshold: float,
    top_k: int,
) -> VisitedPathTrace:
    """确定性生成 OpenViking 风格的分层检索下钻与剪枝实验场数据。"""
    tracer = ContextRetrievalTracer(trace_id=trace_id, query=query)

    # 1. 根分类
    tracer.add_root_node(
        node_id="root-system",
        name="系统核心架构 (System Architecture)",
        path="/knowledge/architecture",
        similarity_score=0.86,
        pruning_threshold=threshold,
        metadata={"category": "tech_spec"},
    )
    tracer.add_root_node(
        node_id="root-biz",
        name="商务与法务合规 (Commercial & Legal)",
        path="/knowledge/legal",
        similarity_score=0.48,
        pruning_threshold=threshold,
        metadata={"category": "compliance"},
    )

    # 根分类 2: 剪枝 (低于阈值)
    if 0.48 < threshold:
        tracer.record_pruning(
            node_id="root-biz",
            reason=PruningReason.SCORE_BELOW_THRESHOLD,
            reason_detail=f"相关度得分 0.480 低于阈值 {threshold:.3f}",
        )

    # 2. 根分类 1 下钻二级子目录
    tracer.add_child_node(
        parent_id="root-system",
        node_id="sub-observe",
        name="可观测性规范 (Observability Specs)",
        path="/knowledge/architecture/observability",
        similarity_score=0.92,
        pruning_threshold=threshold,
    )
    tracer.add_child_node(
        parent_id="root-system",
        node_id="sub-auth",
        name="认证与安全网关 (Auth Gateway)",
        path="/knowledge/architecture/auth",
        similarity_score=0.62,
        pruning_threshold=threshold,
    )

    # 二级目录子分支剪枝判定
    if 0.62 < threshold:
        tracer.record_pruning(
            node_id="sub-auth",
            reason=PruningReason.SCORE_BELOW_THRESHOLD,
            reason_detail=f"相关度得分 0.620 低于阈值 {threshold:.3f}",
        )

    # 3. 三级叶子文档
    leaf_docs = [
        ("leaf-trace", "retrieval_trace_guide.md", "/knowledge/architecture/observability/trace.md", 0.95),
        ("leaf-health", "health_diagnostics.md", "/knowledge/architecture/observability/health.md", 0.88),
        ("leaf-cost", "cost_insights.md", "/knowledge/architecture/observability/cost.md", 0.81),
        ("leaf-legacy", "legacy_metrics.md", "/knowledge/architecture/observability/legacy.md", 0.72),
    ]

    candidates: List[tuple[str, float]] = []
    for doc_id, name, path, score in leaf_docs:
        tracer.add_child_node(
            parent_id="sub-observe",
            node_id=doc_id,
            name=name,
            path=path,
            similarity_score=score,
            pruning_threshold=threshold,
        )
        if score < threshold:
            tracer.record_pruning(
                node_id=doc_id,
                reason=PruningReason.SCORE_BELOW_THRESHOLD,
                reason_detail=f"分值 {score:.3f} 低于阈值 {threshold:.3f}",
            )
        else:
            candidates.append((doc_id, score))

    # Top-K 筛选与溢出剪枝
    candidates.sort(key=lambda x: x[1], reverse=True)
    hit_ids = {c[0] for c in candidates[:top_k]}
    for doc_id, score in candidates[top_k:]:
        tracer.record_pruning(
            node_id=doc_id,
            reason=PruningReason.TOPK_OVERFLOW,
            reason_detail=f"分值达标但超出单轮最大召回 Top-{top_k} 配额",
        )

    for doc_id in hit_ids:
        tracer.record_hit(doc_id)

    return tracer.finalize()


@router.get(
    "/retrieval-traces/{trace_id}",
    response_model=VisitedPathTraceDTO,
    status_code=status.HTTP_200_OK,
    summary="获取指定 Trace ID 的上下文检索决策树与剪枝决策详情",
)
async def get_retrieval_trace(trace_id: str) -> VisitedPathTraceDTO:
    """获取单次会话或查询背后的上下文检索决策树全景轨迹。"""
    trace = _build_simulation_trace(
        trace_id=trace_id,
        query="上下文检索决策树白盒化下钻",
        threshold=0.70,
        top_k=3,
    )
    return _trace_to_dto(trace)


@router.post(
    "/retrieval-traces/simulate",
    response_model=VisitedPathTraceDTO,
    status_code=status.HTTP_200_OK,
    summary="对标 OpenViking Web Studio 实验场：模拟分层检索下钻与动态剪枝计算",
)
async def simulate_retrieval_trace(
    request: RetrievalSimulateRequest,
) -> VisitedPathTraceDTO:
    """检索实验场模拟接口：传入查询词、阈值与 Top-K，即时返回分层下钻决策树与剪枝判定结果。"""
    trace_id = f"sim-{int(time.time() * 1000)}"
    trace = _build_simulation_trace(
        trace_id=trace_id,
        query=request.query,
        threshold=request.pruning_threshold,
        top_k=request.top_k,
    )
    return _trace_to_dto(trace)
