"""
[INPUT]: Model names, token estimations, HTTP response headers, and subagent workspace IDs.
[OUTPUT]: QuotaPacingDecision actions, GovernorLiveStatus telemetry, ProviderQuotaHeaderSnapshot, and SubagentQuotaSlice allocations.
[POS]: myrm-agent/myrm-agent-server/app/api/system/rate_limit_governor_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.rate_limit_governor import (
    GovernorLiveStatus,
    PacingAction,
    ProactivePacingGovernor,
    ProviderQuotaHeaderSnapshot,
    QuotaHeaderSniffer,
    QuotaPacingDecision,
    SubagentQuotaSlice,
    SubagentQuotaSlicer,
)

router = APIRouter(tags=["rate-limit-governor"])

_governor = ProactivePacingGovernor()
_slicer = SubagentQuotaSlicer()


# --- Pydantic Request / Response Models ---

class PacingPreCheckRequest(BaseModel):
    model_name: str
    estimated_prompt_tokens: int = Field(default=1000, ge=0)
    fallback_model: Optional[str] = None


class PacingPreCheckResponse(BaseModel):
    action: str
    delay_ms: int
    current_tpm_usage: int
    max_tpm_limit: int
    tpm_watermark_pct: float
    current_rpm_usage: int
    max_rpm_limit: int
    reason: str
    target_model_or_fallback: str


class RecordUsageRequest(BaseModel):
    model_name: str
    actual_tokens: int = Field(ge=0)


class UpdateHeadersRequest(BaseModel):
    model_name: str
    headers: Dict[str, str] = Field(default_factory=dict)


class HeaderStateResponse(BaseModel):
    model_name: str
    remaining_tokens: Optional[int]
    reset_tokens_seconds: Optional[float]
    remaining_requests: Optional[int]
    reset_requests_seconds: Optional[float]
    retry_after_seconds: Optional[float]
    extracted_at: str


class GovernorStatusResponse(BaseModel):
    model_name: str
    tpm_watermark_pct: float
    rpm_watermark_pct: float
    smoothed_request_count: int
    prevented_429_count: int
    active_subagent_slices_count: int
    status_label: str


class AllocateSliceRequest(BaseModel):
    workspace_id: str
    subagent_id: str
    total_available_tpm: int = Field(default=50_000, gt=0)
    concurrency_count: int = Field(default=1, gt=0)


class SubagentSliceResponse(BaseModel):
    workspace_id: str
    subagent_id: str
    allocated_tpm_share: int
    consumed_tokens_in_window: int
    remaining_tokens_in_window: int
    is_throttled: bool


class RecordSliceConsumptionRequest(BaseModel):
    workspace_id: str
    subagent_id: str
    tokens: int = Field(ge=0)


# --- Helper Converters ---

def _convert_pacing_decision(dec: QuotaPacingDecision) -> PacingPreCheckResponse:
    return PacingPreCheckResponse(
        action=dec.action.value,
        delay_ms=dec.delay_ms,
        current_tpm_usage=dec.current_tpm_usage,
        max_tpm_limit=dec.max_tpm_limit,
        tpm_watermark_pct=dec.tpm_watermark_pct,
        current_rpm_usage=dec.current_rpm_usage,
        max_rpm_limit=dec.max_rpm_limit,
        reason=dec.reason,
        target_model_or_fallback=dec.target_model_or_fallback,
    )


def _convert_status(st: GovernorLiveStatus) -> GovernorStatusResponse:
    return GovernorStatusResponse(
        model_name=st.model_name,
        tpm_watermark_pct=st.tpm_watermark_pct,
        rpm_watermark_pct=st.rpm_watermark_pct,
        smoothed_request_count=st.smoothed_request_count,
        prevented_429_count=st.prevented_429_count,
        active_subagent_slices_count=st.active_subagent_slices_count,
        status_label=st.status_label,
    )


def _convert_slice(sl: SubagentQuotaSlice) -> SubagentSliceResponse:
    return SubagentSliceResponse(
        workspace_id=sl.workspace_id,
        subagent_id=sl.subagent_id,
        allocated_tpm_share=sl.allocated_tpm_share,
        consumed_tokens_in_window=sl.consumed_tokens_in_window,
        remaining_tokens_in_window=sl.remaining_tokens_in_window,
        is_throttled=sl.is_throttled,
    )


# --- HTTP Endpoints ---

@router.post(
    "/rate-limit-governor/pre-check",
    response_model=PacingPreCheckResponse,
    summary="客户端主动流量整形门禁预检 (零 429 顺滑放行)",
)
def pre_check_pacing(payload: PacingPreCheckRequest) -> PacingPreCheckResponse:
    decision = _governor.evaluate_and_pace(
        model_name=payload.model_name,
        estimated_prompt_tokens=payload.estimated_prompt_tokens,
        fallback_model=payload.fallback_model,
    )
    return _convert_pacing_decision(decision)


@router.post(
    "/rate-limit-governor/record-usage",
    summary="实际 Token 消耗回填登记 (更新滑动窗口统计)",
)
def record_usage(payload: RecordUsageRequest) -> Dict[str, str]:
    _governor.record_usage(
        model_name=payload.model_name,
        actual_tokens=payload.actual_tokens,
    )
    return {"status": "ok", "model_name": payload.model_name}


@router.post(
    "/rate-limit-governor/update-headers",
    response_model=HeaderStateResponse,
    summary="嗅探上游提供商响应头权威限流状态",
)
def update_headers(payload: UpdateHeadersRequest) -> HeaderStateResponse:
    snapshot = QuotaHeaderSniffer.sniff(payload.model_name, payload.headers)
    _governor.update_from_header_snapshot(snapshot)
    return HeaderStateResponse(
        model_name=snapshot.model_name,
        remaining_tokens=snapshot.remaining_tokens,
        reset_tokens_seconds=snapshot.reset_tokens_seconds,
        remaining_requests=snapshot.remaining_requests,
        reset_requests_seconds=snapshot.reset_requests_seconds,
        retry_after_seconds=snapshot.retry_after_seconds,
        extracted_at=snapshot.extracted_at,
    )


@router.get(
    "/rate-limit-governor/status",
    response_model=List[GovernorStatusResponse],
    summary="查询所有或指定模型的实时配额水位与限流削峰遥测",
)
def get_live_status(
    model_name: Optional[str] = Query(default=None, description="模型名称，缺省则返回核心模型列表"),
) -> List[GovernorStatusResponse]:
    target_models = (
        [model_name]
        if model_name
        else ["claude-3-5-sonnet", "deepseek-chat", "gpt-4o"]
    )
    results: List[GovernorStatusResponse] = []
    for m in target_models:
        status_obj = _governor.get_live_status(m)
        results.append(_convert_status(status_obj))
    return results


@router.post(
    "/rate-limit-governor/slices/allocate",
    response_model=SubagentSliceResponse,
    summary="为工作区子 Agent 分配隔离的 TPM 配额切片",
)
def allocate_slice(payload: AllocateSliceRequest) -> SubagentSliceResponse:
    slice_entry = _slicer.allocate_slice(
        workspace_id=payload.workspace_id,
        subagent_id=payload.subagent_id,
        total_available_tpm=payload.total_available_tpm,
        concurrency_count=payload.concurrency_count,
    )
    return _convert_slice(slice_entry)


@router.get(
    "/rate-limit-governor/slices",
    response_model=List[SubagentSliceResponse],
    summary="查询工作区下所有子 Agent 配额切片",
)
def list_slices(
    workspace_id: str = Query(..., description="工作区唯一标识"),
) -> List[SubagentSliceResponse]:
    slices = _slicer.list_slices_for_workspace(workspace_id)
    return [_convert_slice(s) for s in slices]


@router.post(
    "/rate-limit-governor/slices/consume",
    response_model=SubagentSliceResponse,
    summary="子 Agent Token 消耗登记并判断是否触发切片熔断",
)
def consume_slice(payload: RecordSliceConsumptionRequest) -> SubagentSliceResponse:
    updated = _slicer.record_consumption(
        workspace_id=payload.workspace_id,
        subagent_id=payload.subagent_id,
        tokens=payload.tokens,
    )
    return _convert_slice(updated)


@router.post(
    "/rate-limit-governor/slices/reset",
    summary="重置工作区子 Agent 切片配额窗口",
)
def reset_slices(
    workspace_id: Optional[str] = Query(default=None, description="工作区唯一标识，缺省则重置全局切片"),
) -> Dict[str, str]:
    _slicer.reset_window(workspace_id=workspace_id)
    return {"status": "ok", "workspace_id": workspace_id or "all"}
