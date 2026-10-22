"""
[INPUT]: Local sink configuration, span record payloads, and query filters.
[OUTPUT]: LocalSinkStatusResponse, LocalSpanModel lists, and REST endpoints for disk persistence fallback.
[POS]: myrm-agent/myrm-agent-server/app/api/system/local_sink_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.local_sink import (
    LocalDiskTelemetrySink,
    LocalSinkStatus,
    LocalSpanRecord,
)

router = APIRouter(tags=["local-sink"])

_sink = LocalDiskTelemetrySink()


# --- Pydantic Schemas ---

class LocalSpanModel(BaseModel):
    trace_id: str
    span_id: str
    name: str
    start_time_iso: str
    end_time_iso: str
    duration_ms: float
    status: str
    attributes: Dict[str, str]


class ConfigureLocalSinkRequest(BaseModel):
    enabled: bool
    storage_path: Optional[str] = None


class LocalSinkStatusResponse(BaseModel):
    is_enabled: bool
    sink_path: str
    buffered_spans_count: int
    persisted_spans_count: int
    file_size_bytes: int
    last_flush_iso: Optional[str]


class RecordSpanRequest(BaseModel):
    trace_id: str
    span_id: str
    name: str
    duration_ms: float
    status: str = "OK"
    attributes: Dict[str, str] = Field(default_factory=dict)


# --- Helper Converters ---

def _to_span_model(s: LocalSpanRecord) -> LocalSpanModel:
    return LocalSpanModel(
        trace_id=s.trace_id,
        span_id=s.span_id,
        name=s.name,
        start_time_iso=s.start_time_iso,
        end_time_iso=s.end_time_iso,
        duration_ms=s.duration_ms,
        status=s.status,
        attributes=s.attributes,
    )


def _to_status_response(status: LocalSinkStatus) -> LocalSinkStatusResponse:
    return LocalSinkStatusResponse(
        is_enabled=status.is_enabled,
        sink_path=status.sink_path,
        buffered_spans_count=status.buffered_spans_count,
        persisted_spans_count=status.persisted_spans_count,
        file_size_bytes=status.file_size_bytes,
        last_flush_iso=status.last_flush_iso,
    )


# --- Endpoints ---

@router.post(
    "/local-sink/config",
    response_model=LocalSinkStatusResponse,
    summary="配置本地盘可观测性落盘兜底引擎（开启/关闭 Opt-In 本地 JSONL 持久化）",
)
def configure_local_sink(payload: ConfigureLocalSinkRequest) -> LocalSinkStatusResponse:
    _sink.set_enabled(payload.enabled)
    return _to_status_response(_sink.get_status())


@router.get(
    "/local-sink/status",
    response_model=LocalSinkStatusResponse,
    summary="获取当前本地盘 Telemetry Sink 运行状态（落盘文件大小、缓冲条数、刷新时间）",
)
def get_local_sink_status() -> LocalSinkStatusResponse:
    return _to_status_response(_sink.get_status())


@router.get(
    "/local-sink/spans",
    response_model=List[LocalSpanModel],
    summary="查询最近捕获的本地调用链 Spans 列表（内存环形缓冲区快速回放）",
)
def get_recent_spans(
    limit: int = Query(default=50, ge=1, le=500),
) -> List[LocalSpanModel]:
    spans = _sink.get_recent_spans(limit=limit)
    return [_to_span_model(s) for s in spans]


@router.post(
    "/local-sink/record-span",
    response_model=LocalSpanModel,
    summary="上报/模拟一条 Span 到本地可观测性兜底 Sink",
)
def record_local_span(payload: RecordSpanRequest) -> LocalSpanModel:
    span = _sink.record_span(
        trace_id=payload.trace_id,
        span_id=payload.span_id,
        name=payload.name,
        duration_ms=payload.duration_ms,
        status=payload.status,
        attributes=payload.attributes,
    )
    return _to_span_model(span)
