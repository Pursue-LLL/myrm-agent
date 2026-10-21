"""
[INPUT]: Messages payload, system prompt content, window configuration, and provider reported actual tokens.
[OUTPUT]: ContextBreakdownResponse, ContextThresholdsResponse, and REST endpoints for seven-category breakdown and 60%/90% alert boundaries.
[POS]: myrm-agent/myrm-agent-server/app/api/system/context_breakdown_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.context_breakdown import (
    ContextAlertLevel,
    ContextBreakdownResolver,
    ContextBreakdownSnapshot,
    ContextCategoryShare,
)

router = APIRouter(tags=["context-breakdown"])

_resolver = ContextBreakdownResolver()


# --- Pydantic Schemas ---

class ContextCategoryShareModel(BaseModel):
    category: str
    label_zh: str
    estimated_tokens: int
    percentage: float
    color_hex: str


class ResolveContextBreakdownRequest(BaseModel):
    system_content: Optional[str] = None
    messages: Optional[List[Dict[str, str]]] = None
    tools_schema_tokens: int = 0
    provider_actual_tokens: int = 0
    total_window_tokens: int = 128000


class ContextBreakdownResponse(BaseModel):
    total_window_tokens: int
    provider_actual_tokens: int
    estimated_sum_tokens: int
    usage_ratio_pct: float
    alert_level: str
    alert_message: str
    categories: Dict[str, ContextCategoryShareModel]


class ContextThresholdsResponse(BaseModel):
    default_window_tokens: int
    warning_ratio_pct: float
    critical_ratio_pct: float
    recommended_action_60: str
    recommended_action_90: str


# --- Helper Converters ---

def _to_share_model(s: ContextCategoryShare) -> ContextCategoryShareModel:
    return ContextCategoryShareModel(
        category=s.category,
        label_zh=s.label_zh,
        estimated_tokens=s.estimated_tokens,
        percentage=s.percentage,
        color_hex=s.color_hex,
    )


def _to_response(snap: ContextBreakdownSnapshot) -> ContextBreakdownResponse:
    return ContextBreakdownResponse(
        total_window_tokens=snap.total_window_tokens,
        provider_actual_tokens=snap.provider_actual_tokens,
        estimated_sum_tokens=snap.estimated_sum_tokens,
        usage_ratio_pct=snap.usage_ratio_pct,
        alert_level=snap.alert_level.value,
        alert_message=snap.alert_message,
        categories={k: _to_share_model(v) for k, v in snap.categories.items()},
    )


# --- Endpoints ---

@router.post(
    "/context-breakdown/resolve",
    response_model=ContextBreakdownResponse,
    summary="解析上下文用量七分类占比明细与 60%/90% 警戒线评估（消除余量为 0 黑盒，并列展示估算与提供商实报）",
)
def resolve_context_breakdown(payload: ResolveContextBreakdownRequest) -> ContextBreakdownResponse:
    snap = _resolver.resolve(
        system_content=payload.system_content,
        messages=payload.messages,
        tools_schema_tokens=payload.tools_schema_tokens,
        provider_actual_tokens=payload.provider_actual_tokens,
        total_window_tokens=payload.total_window_tokens,
    )
    return _to_response(snap)


@router.get(
    "/context-breakdown/thresholds",
    response_model=ContextThresholdsResponse,
    summary="获取上下文警戒线标准配置（60% 性能衰减警戒线与 90% 自动压缩熔断线）",
)
def get_context_thresholds() -> ContextThresholdsResponse:
    return ContextThresholdsResponse(
        default_window_tokens=128000,
        warning_ratio_pct=60.0,
        critical_ratio_pct=90.0,
        recommended_action_60="跨越 60% 注意力衰减临界点，建议主动压缩上下文、截断工具历史输出或新开任务。",
        recommended_action_90="达到 90% 极高警戒线，系统将触发自动深度压缩或硬预算熔断以防调用失败。",
    )
