"""
[INPUT]: Metric evaluation payloads or window query parameters.
[OUTPUT]: KnowledgeCompoundingHealthResponse containing overall score, 5-metric cards, and regression alerts.
[POS]: myrm-agent/myrm-agent-server/app/api/system/knowledge_compounding_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.knowledge_compounding import (
    CompoundingMetricName,
    CompoundingMetricPoint,
    KnowledgeCompoundingAggregator,
    KnowledgeCompoundingHealthSnapshot,
    MetricHealthStatus,
)

router = APIRouter(tags=["knowledge-compounding"])

_aggregator = KnowledgeCompoundingAggregator()


# --- Pydantic Schemas ---

class CompoundingMetricPointResponse(BaseModel):
    name: str
    value: float
    unit: str
    status: str
    benchmark_threshold: float
    description: str
    data_source_origin: str


class KnowledgeCompoundingHealthResponse(BaseModel):
    overall_score: float
    compounding_tier: str
    metrics: Dict[str, CompoundingMetricPointResponse]
    regression_alerts: List[str]
    evaluated_at: str
    window_days: int


class EvaluateKnowledgeCompoundingRequest(BaseModel):
    repeated_error_rate_pct: float = Field(default=3.5, ge=0.0, le=100.0)
    knowledge_hit_rate_pct: float = Field(default=68.0, ge=0.0, le=100.0)
    human_corrections_count: int = Field(default=4, ge=0)
    first_pass_success_rate_pct: float = Field(default=88.5, ge=0.0, le=100.0)
    stale_knowledge_ratio_pct: float = Field(default=8.0, ge=0.0, le=100.0)
    window_days: int = Field(default=30, ge=1, le=365)


# --- Helper Converters ---

def _to_response_model(snapshot: KnowledgeCompoundingHealthSnapshot) -> KnowledgeCompoundingHealthResponse:
    metrics_dict: Dict[str, CompoundingMetricPointResponse] = {}
    for key, pt in snapshot.metrics.items():
        metrics_dict[key] = CompoundingMetricPointResponse(
            name=pt.name.value,
            value=pt.value,
            unit=pt.unit,
            status=pt.status.value,
            benchmark_threshold=pt.benchmark_threshold,
            description=pt.description,
            data_source_origin=pt.data_source_origin,
        )

    return KnowledgeCompoundingHealthResponse(
        overall_score=snapshot.overall_score,
        compounding_tier=snapshot.compounding_tier,
        metrics=metrics_dict,
        regression_alerts=snapshot.regression_alerts,
        evaluated_at=snapshot.evaluated_at,
        window_days=snapshot.window_days,
    )


# --- Endpoints ---

@router.get(
    "/knowledge-compounding/scoreboard",
    response_model=KnowledgeCompoundingHealthResponse,
    summary="查询 Agent 知识复利五大核心闭环指标健康度记分板与综合进化指数",
)
def get_compounding_scoreboard(
    window_days: int = Query(default=30, ge=1, le=365, description="统计分析滑动窗口天数")
) -> KnowledgeCompoundingHealthResponse:
    snapshot = _aggregator.evaluate(window_days=window_days)
    return _to_response_model(snapshot)


@router.post(
    "/knowledge-compounding/evaluate",
    response_model=KnowledgeCompoundingHealthResponse,
    summary="即时聚合评测知识复利五大闭环指标快照并触发劣化预警扫描",
)
def evaluate_compounding_health(
    payload: EvaluateKnowledgeCompoundingRequest,
) -> KnowledgeCompoundingHealthResponse:
    snapshot = _aggregator.evaluate(
        repeated_error_rate_pct=payload.repeated_error_rate_pct,
        knowledge_hit_rate_pct=payload.knowledge_hit_rate_pct,
        human_corrections_count=payload.human_corrections_count,
        first_pass_success_rate_pct=payload.first_pass_success_rate_pct,
        stale_knowledge_ratio_pct=payload.stale_knowledge_ratio_pct,
        window_days=payload.window_days,
    )
    return _to_response_model(snapshot)
