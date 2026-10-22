"""
[INPUT]: Probe requests, simulation flags, and OTel posture queries.
[OUTPUT]: OtelDegradeStatusResponse and active probe confirmation responses.
[POS]: myrm-agent/myrm-agent-server/app/api/system/otel_degrade_api.py
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.otel_degrade import (
    GracefulOtelRuntime,
    OtelDegradeStatus,
    OtelPostureState,
)

router = APIRouter(tags=["otel-degrade"])

_runtime = GracefulOtelRuntime()


# --- Pydantic Schemas ---

class OtelDegradeStatusResponse(BaseModel):
    state: str  # ACTIVE | DEGRADED_NO_OP | DISABLED
    is_otel_installed: bool
    degrade_reason: Optional[str]
    intercepted_spans_count: int
    intercepted_metrics_count: int
    last_probe_time: str


class SimulateMissingRequest(BaseModel):
    simulate_missing: bool = Field(
        ...,
        description="是否在运行时模拟 opentelemetry 依赖库缺失（用于故障注入与降级测试）",
    )


class SimulateMissingResponse(BaseModel):
    simulating_missing: bool
    current_status: OtelDegradeStatusResponse


# --- Helper Converters ---

def _to_response(status_obj: OtelDegradeStatus) -> OtelDegradeStatusResponse:
    return OtelDegradeStatusResponse(
        state=status_obj.state.value,
        is_otel_installed=status_obj.is_otel_installed,
        degrade_reason=status_obj.degrade_reason,
        intercepted_spans_count=status_obj.intercepted_spans_count,
        intercepted_metrics_count=status_obj.intercepted_metrics_count,
        last_probe_time=status_obj.last_probe_time,
    )


# --- Endpoints ---

@router.get(
    "/otel-degrade/status",
    response_model=OtelDegradeStatusResponse,
    summary="查询当前 OpenTelemetry 探针运行姿态与零硬依赖降级状态",
)
def get_otel_degrade_status() -> OtelDegradeStatusResponse:
    stat = _runtime.probe_status()
    return _to_response(stat)


@router.post(
    "/otel-degrade/probe",
    response_model=OtelDegradeStatusResponse,
    summary="主动触发一次 OpenTelemetry 探针依赖与运行态自检",
)
def trigger_otel_probe() -> OtelDegradeStatusResponse:
    stat = _runtime.probe_status()
    return _to_response(stat)


@router.post(
    "/otel-degrade/simulate",
    response_model=SimulateMissingResponse,
    summary="模拟或还原 OpenTelemetry 依赖缺失（测试/故障注入专用）",
)
def simulate_dependency_missing(payload: SimulateMissingRequest) -> SimulateMissingResponse:
    _runtime.simulate_missing_dependency(payload.simulate_missing)
    stat = _runtime.probe_status()
    return SimulateMissingResponse(
        simulating_missing=payload.simulate_missing,
        current_status=_to_response(stat),
    )
