"""FastAPI router for external agent onboarding insight sampling and reporting.

[POS]
历史会话轻量采样与“初见报告”极速冷启动 HTTP 接入层。
暴露宿主机 Agent 目录探测、多源关键帧滑动提取与初见画像生成、以及用户确认后批量记忆原子入库。

[INPUT]
- app.schemas.onboarding_insight DTOs
- app.services.memory.onboarding::get_onboarding_insight_service

[OUTPUT]
- router: Agent 历史接入与初见报告 REST 路由
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.onboarding_insight import (
    ConfirmInsightIngestRequest,
    ConfirmInsightIngestResponse,
    FirstEncounterReportResponse,
    GenerateFirstEncounterReportRequest,
    OnboardingScanSummaryResponse,
    ScanAgentSourcesRequest,
)
from app.services.memory.onboarding import get_onboarding_insight_service

router = APIRouter(prefix="/onboarding", tags=["memory-onboarding-insight"])


@router.post(
    "/scan-sources",
    response_model=OnboardingScanSummaryResponse,
    summary="Probe host machine for active external agent directories",
)
def scan_sources(request: ScanAgentSourcesRequest) -> OnboardingScanSummaryResponse:
    """Detect available agent sources on host."""
    service = get_onboarding_insight_service()
    return service.scan_sources(request)


@router.post(
    "/generate-report",
    response_model=FirstEncounterReportResponse,
    summary="Sample historical keyframes and generate first-encounter report",
)
def generate_report(request: GenerateFirstEncounterReportRequest) -> FirstEncounterReportResponse:
    """Sample session files and generate structured tech profile report."""
    service = get_onboarding_insight_service()
    return service.generate_report(request)


@router.post(
    "/confirm-ingest",
    response_model=ConfirmInsightIngestResponse,
    summary="Confirm and batch ingest selected insight facts into persistent memory",
)
def confirm_ingest(request: ConfirmInsightIngestRequest) -> ConfirmInsightIngestResponse:
    """Persist selected insight facts into target agent or global memory."""
    service = get_onboarding_insight_service()
    return service.confirm_ingest(request)
