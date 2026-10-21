"""
[INPUT]: Turn round usage payloads, session/turn IDs, and gateway shape rewrite queries.
[OUTPUT]: TurnUsageSummaryResponse, RewriteShapeResponse, and REST endpoints for dual-count billed usage.
[POS]: myrm-agent/myrm-agent-server/app/api/system/turn_usage_api.py
"""

from typing import Dict, Optional, Union

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.turn_usage import (
    NormalizedUsage,
    TurnUsageSummary,
    TurnUsageTracker,
)

router = APIRouter(tags=["turn-usage"])

_tracker = TurnUsageTracker()


# --- Pydantic Models ---

class NormalizedUsageModel(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read: Optional[int] = None
    cache_write: Optional[int] = None


class RecordTurnRoundRequest(BaseModel):
    session_id: str
    turn_id: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read: Optional[int] = None
    cache_write: Optional[int] = None


class TurnUsageSummaryResponse(BaseModel):
    session_id: str
    turn_id: str
    rounds_count: int
    billed: NormalizedUsageModel
    freeze_usage: NormalizedUsageModel
    cache_divergence_tokens: int
    created_at: str
    updated_at: str


class RewriteShapeRequest(BaseModel):
    existing_shape: Dict[str, Union[int, Dict[str, int]]]
    billed: NormalizedUsageModel


class RewriteShapeResponse(BaseModel):
    rewritten: Dict[str, Union[int, Dict[str, int]]]


# --- Helper Converters ---

def _to_model(u: NormalizedUsage) -> NormalizedUsageModel:
    return NormalizedUsageModel(
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        cache_read=u.cache_read,
        cache_write=u.cache_write,
    )


def _to_summary_response(s: TurnUsageSummary) -> TurnUsageSummaryResponse:
    return TurnUsageSummaryResponse(
        session_id=s.session_id,
        turn_id=s.turn_id,
        rounds_count=s.rounds_count,
        billed=_to_model(s.billed),
        freeze_usage=_to_model(s.freeze_usage),
        cache_divergence_tokens=s.cache_divergence_tokens,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


# --- Endpoints ---

@router.post(
    "/turn-usage/record-round",
    response_model=TurnUsageSummaryResponse,
    summary="记录回合内单次物理调用的 Token 使用量（自动更新 billed 累加与 freeze 最新缓存状态）",
)
def record_turn_round(payload: RecordTurnRoundRequest) -> TurnUsageSummaryResponse:
    usage = NormalizedUsage(
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        cache_read=payload.cache_read,
        cache_write=payload.cache_write,
    )
    summary = _tracker.record_round(
        session_id=payload.session_id,
        turn_id=payload.turn_id,
        usage=usage,
    )
    return _to_summary_response(summary)


@router.get(
    "/turn-usage/summary/{session_id}/{turn_id}",
    response_model=TurnUsageSummaryResponse,
    summary="获取指定回合的双计数汇总（对比 billed 真实账单与 freeze 缓存冻结决策状态）",
)
def get_turn_usage_summary(session_id: str, turn_id: str) -> TurnUsageSummaryResponse:
    summary = _tracker.get_summary(session_id, turn_id)
    return _to_summary_response(summary)


@router.post(
    "/turn-usage/rewrite-shape",
    response_model=RewriteShapeResponse,
    summary="将 billed 累加使用量自适应回写至下游网关原始响应形状（保留 OpenAI/Anthropic 原生键名）",
)
def rewrite_usage_shape(payload: RewriteShapeRequest) -> RewriteShapeResponse:
    billed = NormalizedUsage(
        input_tokens=payload.billed.input_tokens,
        output_tokens=payload.billed.output_tokens,
        cache_read=payload.billed.cache_read,
        cache_write=payload.billed.cache_write,
    )
    rewritten = _tracker.write_in_shape(payload.existing_shape, billed)
    return RewriteShapeResponse(rewritten=rewritten)
