"""
[INPUT]: Stream call lifecycle events, chunk notifications, termination outcome verdicts, and filter queries.
[OUTPUT]: StreamCallSessionResponse, StreamMetricsAggregateResponse, and clean metric endpoints.
[POS]: myrm-agent/myrm-agent-server/app/api/system/stream_metrics_api.py
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.stream_metrics import (
    StreamCallMetricsCollector,
    StreamCallOutcome,
    StreamCallSession,
    StreamMetricsAggregate,
)

router = APIRouter(tags=["stream-metrics"])

_collector = StreamCallMetricsCollector()


# --- Pydantic Request & Response Schemas ---

class StartCallRequest(BaseModel):
    call_id: str
    model_name: str
    provider: str = "openai"


class RecordChunkRequest(BaseModel):
    call_id: str
    chunk_tokens: int = Field(default=0, ge=0)
    is_first_token: bool = False


class FinalizeCallRequest(BaseModel):
    call_id: str
    outcome: str = "SUCCESS"  # SUCCESS | ERROR | CANCELLED | TIMEOUT
    error_message: Optional[str] = None


class StreamCallSessionResponse(BaseModel):
    call_id: str
    model_name: str
    provider: str
    start_time_ms: float
    ttft_ms: Optional[float]
    end_time_ms: Optional[float]
    total_duration_ms: Optional[float]
    chunk_count: int
    total_tokens: int
    outcome: Optional[str]
    error_message: Optional[str]
    is_finalized: bool


class StreamMetricsAggregateResponse(BaseModel):
    total_calls: int
    success_calls: int
    error_calls: int
    cancelled_calls: int
    timeout_calls: int
    total_chunks: int
    total_tokens: int
    avg_ttft_ms: float
    avg_duration_ms: float
    success_rate_pct: float
    chunk_inflation_ratio: float


# --- Helper Converters ---

def _to_session_response(s: StreamCallSession) -> StreamCallSessionResponse:
    return StreamCallSessionResponse(
        call_id=s.call_id,
        model_name=s.model_name,
        provider=s.provider,
        start_time_ms=s.start_time_ms,
        ttft_ms=s.ttft_ms,
        end_time_ms=s.end_time_ms,
        total_duration_ms=s.total_duration_ms,
        chunk_count=s.chunk_count,
        total_tokens=s.total_tokens,
        outcome=s.outcome.value if s.outcome else None,
        error_message=s.error_message,
        is_finalized=s.is_finalized,
    )


def _to_aggregate_response(agg: StreamMetricsAggregate) -> StreamMetricsAggregateResponse:
    return StreamMetricsAggregateResponse(
        total_calls=agg.total_calls,
        success_calls=agg.success_calls,
        error_calls=agg.error_calls,
        cancelled_calls=agg.cancelled_calls,
        timeout_calls=agg.timeout_calls,
        total_chunks=agg.total_chunks,
        total_tokens=agg.total_tokens,
        avg_ttft_ms=agg.avg_ttft_ms,
        avg_duration_ms=agg.avg_duration_ms,
        success_rate_pct=agg.success_rate_pct,
        chunk_inflation_ratio=agg.chunk_inflation_ratio,
    )


# --- Endpoints ---

@router.post(
    "/stream-metrics/session/start",
    response_model=StreamCallSessionResponse,
    summary="开启流式调用生命周期跟踪",
)
def start_call_session(payload: StartCallRequest) -> StreamCallSessionResponse:
    session = _collector.start_call(
        call_id=payload.call_id,
        model_name=payload.model_name,
        provider=payload.provider,
    )
    return _to_session_response(session)


@router.post(
    "/stream-metrics/session/chunk",
    response_model=Optional[StreamCallSessionResponse],
    summary="上报流中间 chunk 事件（仅增量累积数据，绝不增加独立调用次数）",
)
def record_call_chunk(payload: RecordChunkRequest) -> Optional[StreamCallSessionResponse]:
    session = _collector.record_chunk(
        call_id=payload.call_id,
        chunk_tokens=payload.chunk_tokens,
        is_first_token=payload.is_first_token,
    )
    if not session:
        return None
    return _to_session_response(session)


@router.post(
    "/stream-metrics/session/finalize",
    response_model=StreamCallSessionResponse,
    summary="流式调用终态结算（幂等操作，仅产生唯一次最终结果归因）",
)
def finalize_call_session(payload: FinalizeCallRequest) -> StreamCallSessionResponse:
    try:
        outcome_enum = StreamCallOutcome(payload.outcome)
    except ValueError:
        outcome_enum = StreamCallOutcome.SUCCESS

    session = _collector.finalize_call(
        call_id=payload.call_id,
        outcome=outcome_enum,
        error_message=payload.error_message,
    )
    return _to_session_response(session)


@router.get(
    "/stream-metrics/aggregate",
    response_model=StreamMetricsAggregateResponse,
    summary="获取流式调用无污染聚合统计大盘（排除中间 Chunk 计数虚高）",
)
def get_stream_metrics_aggregate(
    model_name: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
) -> StreamMetricsAggregateResponse:
    agg = _collector.get_aggregate(model_name=model_name, provider=provider)
    return _to_aggregate_response(agg)


@router.get(
    "/stream-metrics/session/{call_id}",
    response_model=StreamCallSessionResponse,
    summary="查询单次流式调用的详细指标追踪",
)
def get_call_session(call_id: str) -> StreamCallSessionResponse:
    session = _collector.get_session(call_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stream call session '{call_id}' not found",
        )
    return _to_session_response(session)
