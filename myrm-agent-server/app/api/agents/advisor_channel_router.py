"""
[INPUT]
- fastapi (APIRouter, Depends, status)
- app.schemas.advisor_channel (
    AdvisorReviewResultDTO,
    AdvisorReviewStepRequestDTO,
    AdvisorSessionReviewsResponseDTO,
  )
- app.services.agent.advisor_channel_service (
    AdvisorChannelService,
    get_advisor_channel_service,
  )

[OUTPUT]
- router: 双模型实时旁路军师评审通道 REST API 路由对象

[POS]
Server 业务层双模型实时旁路军师评审通道 HTTP 端点（Topic 12 · 第 17 项）。
暴露单步动作审查接口、会话历史干预记录查询与阻断重置接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.advisor_channel import (
    AdvisorReviewResultDTO,
    AdvisorReviewStepRequestDTO,
    AdvisorSessionReviewsResponseDTO,
)
from app.services.agent.advisor_channel_service import (
    AdvisorChannelService,
    get_advisor_channel_service,
)

router = APIRouter(prefix="/advisor-channel", tags=["advisor-channel"])


@router.post(
    "/review",
    response_model=AdvisorReviewResultDTO,
    status_code=status.HTTP_200_OK,
    summary="对主 Agent 单步动作执行双模型实时旁路军师审查",
)
async def review_step(
    request: AdvisorReviewStepRequestDTO,
    service: AdvisorChannelService = Depends(get_advisor_channel_service),
) -> AdvisorReviewResultDTO:
    """
    独立旁路审查主模型的 Tool 调用，生成 aside、concern 或 blocker 级别干预。
    """
    return service.review_step(request)


@router.get(
    "/sessions/{session_id}",
    response_model=AdvisorSessionReviewsResponseDTO,
    summary="获取指定会话的全量旁路审查干预记录",
)
async def get_session_reviews(
    session_id: str,
    service: AdvisorChannelService = Depends(get_advisor_channel_service),
) -> AdvisorSessionReviewsResponseDTO:
    """查询该会话累计的所有审查干预建议、总审查次数与硬阻断计数。"""
    return service.get_session_reviews(session_id)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="清空指定会话的旁路审查记录",
)
async def clear_session_reviews(
    session_id: str,
    service: AdvisorChannelService = Depends(get_advisor_channel_service),
) -> None:
    """重置该会话的军师审查历史。"""
    service.clear_session_reviews(session_id)
