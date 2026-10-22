"""[INPUT]
- fastapi::{APIRouter, status}
- pydantic::{BaseModel, Field}
- app.core.infra.health.failure_triage::{
    AgentFailureTriageService,
    BreakpointStage,
    FailureSymptom,
    NegativeOutcome,
    RedispatchRequest,
    RedispatchResponse,
    TriageReport,
  }

[OUTPUT]
- router: APIRouter for failure triage and in-place redispatch
- TriageRequest: 分诊请求 DTO

[POS]
app/api/system/failure_triage_api.py — 失效表象自动分诊与就地重发 HTTP 端点。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.infra.health.failure_triage import (
    AgentFailureTriageService,
    BreakpointStage,
    FailureSymptom,
    NegativeOutcome,
    RedispatchRequest,
    RedispatchResponse,
    TriageReport,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system-failure-triage"])

_triage_service = AgentFailureTriageService()


class TriageRequest(BaseModel):
    """失效自动分诊请求模型。"""

    symptom: FailureSymptom = Field(..., description="用户或系统观察到的失效表象")
    chat_id: str = Field(..., description="异常会话 ID")
    trace_id: str | None = Field(None, description="因果 Trace ID (若有)")
    mock_failure_stage: BreakpointStage | None = Field(None, description="诊断演练模拟注入断点 (可选)")
    mock_negative_outcome: NegativeOutcome | None = Field(None, description="模拟注入负例语义 (可选)")


@router.post(
    "/failure-triage",
    response_model=TriageReport,
    status_code=status.HTTP_200_OK,
    summary="对 Agent 经典失效表象执行六断点决策树自动分诊",
)
async def perform_failure_triage(payload: TriageRequest) -> TriageReport:
    """针对‘无回复’、‘响应极慢’、‘误调工具’或‘网关超时’四大表象，精准穿透六大断点定位根因与自愈方案。"""
    logger.info(
        "Performing failure triage for chat %s (symptom: %s)",
        payload.chat_id,
        payload.symptom,
    )
    return await _triage_service.triage_failure(
        symptom=payload.symptom,
        chat_id=payload.chat_id,
        trace_id=payload.trace_id,
        mock_failure_stage=payload.mock_failure_stage,
        mock_negative_outcome=payload.mock_negative_outcome,
    )


@router.post(
    "/failure-triage/redispatch",
    response_model=RedispatchResponse,
    status_code=status.HTTP_200_OK,
    summary="在指定断点就地重发并恢复事件投递",
)
async def redispatch_event(payload: RedispatchRequest) -> RedispatchResponse:
    """对已完成推理但在投递层中断的请求，提供就地重新投递自愈，无需用户重开新会话。"""
    logger.info(
        "Redispatching event for chat %s at stage %s",
        payload.chat_id,
        payload.stage,
    )
    return await _triage_service.redispatch_event(
        chat_id=payload.chat_id,
        stage=payload.stage,
    )
