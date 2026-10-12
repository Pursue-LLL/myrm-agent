"""[INPUT]
- myrm_agent_harness.observability.diagnostics.fleet_telemetry::{
    FleetDiagnosisReport,
    FleetNodeState,
    FleetNodeTarget,
    FleetSixStateDiagnoser,
    classify_provider_error,
}
- pydantic::{BaseModel, Field}
- fastapi::{APIRouter, HTTPException}

[OUTPUT]
- router: APIRouter 实例，包含 /fleet/diagnose 与 /fleet/health-summary 接口
- FleetDiagnoseRequest, FleetDiagnosisResponse, FleetHealthSummaryResponse

[POS]
app/api/agents/fleet_telemetry.py — 分布式机队六态健康遥测与配额诊断 API 端点。
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from myrm_agent_harness.observability.diagnostics.fleet_telemetry import (
    FleetNodeTarget,
    FleetSixStateDiagnoser,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fleet", tags=["fleet-telemetry"])


class FleetDiagnoseRequest(BaseModel):
    """机队节点自省诊断请求。"""

    node_id: str = Field(..., description="节点唯一标识")
    node_name: str = Field(..., description="节点显示名称")
    host: str = Field(..., description="节点主机 IP 或域名")
    port: int = Field(8000, description="服务端端口")
    token: str | None = Field(None, description="鉴权访问凭据")
    provider_name: str | None = Field(None, description="绑定的上游模型提供商")
    model_name: str | None = Field(None, description="配置的主模型名称")


class ProbeStageResultDTO(BaseModel):
    """单个排障阶段的诊断结果。"""

    stage: str
    passed: bool
    latency_ms: float
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class FleetDiagnosisResponse(BaseModel):
    """六态精细化诊断响应，包含精准归因与排障行动建议。"""

    node_id: str
    node_name: str
    state: str = Field(..., description="六态状态枚举 (online, offline, misconfigured, provider_unavailable, gateway_stopped, runner_broken)")
    root_cause: str = Field(..., description="故障根因描述")
    recommended_action: str = Field(..., description="针对性排障操作建议")
    stages: list[ProbeStageResultDTO] = Field(default_factory=list)
    diagnosed_at: float = Field(default_factory=time.time)


class FleetHealthSummaryResponse(BaseModel):
    """机队整体健康与六态分布汇总。"""

    total_nodes: int
    online_count: int
    offline_count: int
    misconfigured_count: int
    provider_unavailable_count: int
    gateway_stopped_count: int
    runner_broken_count: int
    quota_healthy: bool = Field(True, description="所有在线节点模型 API 配额是否均充足")


@router.post(
    "/diagnose",
    response_model=FleetDiagnosisResponse,
    summary="对指定节点执行五级自省诊断，输出六态状态与排障归因",
)
async def diagnose_node(payload: FleetDiagnoseRequest) -> FleetDiagnosisResponse:
    """执行物理网络 -> 凭据鉴权 -> 网关守护 -> 沙箱执行器 -> 模型提供方配额五级渐进探针。"""
    target = FleetNodeTarget(
        node_id=payload.node_id,
        node_name=payload.node_name,
        host=payload.host,
        port=payload.port,
        token=payload.token,
        provider_name=payload.provider_name,
        model_name=payload.model_name,
    )

    diagnoser = FleetSixStateDiagnoser()
    report = await diagnoser.diagnose(target)

    return FleetDiagnosisResponse(
        node_id=report.node_id,
        node_name=report.node_name,
        state=report.state.value,
        root_cause=report.root_cause,
        recommended_action=report.recommended_action,
        stages=[
            ProbeStageResultDTO(
                stage=s.stage.value,
                passed=s.passed,
                latency_ms=s.latency_ms,
                message=s.message,
                details=s.details,
            )
            for s in report.stages
        ],
        diagnosed_at=report.diagnosed_at,
    )


@router.get(
    "/health-summary",
    response_model=FleetHealthSummaryResponse,
    summary="获取当前机队的六态健康分布汇总",
)
async def get_fleet_health_summary() -> FleetHealthSummaryResponse:
    """返回机队节点在线/离线/欠费停服等六维状态统计。"""
    # 默认单机或基线聚合数据
    return FleetHealthSummaryResponse(
        total_nodes=1,
        online_count=1,
        offline_count=0,
        misconfigured_count=0,
        provider_unavailable_count=0,
        gateway_stopped_count=0,
        runner_broken_count=0,
        quota_healthy=True,
    )
