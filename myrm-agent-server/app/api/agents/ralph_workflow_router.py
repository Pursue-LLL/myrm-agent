"""
[INPUT]
- fastapi (APIRouter, Depends, HTTPException, status)
- app.schemas.ralph_workflow (
    AdvanceRalphRoundRequestDTO,
    CreateRalphSessionRequestDTO,
    RalphSessionResponseDTO,
  )
- app.services.agent.ralph_workflow_service (
    RalphWorkflowService,
    get_ralph_workflow_service,
  )

[OUTPUT]
- router: Ralph 式 Fresh-Agent 多轮循环 REST API 路由对象

[POS]
Server 业务层 Ralph 式 Fresh-Agent 多轮循环 HTTP 端点（Topic 12 · 第 15 项）。
暴露 Ralph 循环会话创建、状态轮询与单轮五字段交接归档端点，对齐 DSH Ralph 编排规范。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.ralph_workflow import (
    AdvanceRalphRoundRequestDTO,
    CreateRalphSessionRequestDTO,
    RalphSessionResponseDTO,
)
from app.services.agent.ralph_workflow_service import (
    RalphWorkflowService,
    get_ralph_workflow_service,
)

router = APIRouter(prefix="/ralph-loop", tags=["ralph-workflow"])


@router.post(
    "/sessions",
    response_model=RalphSessionResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Ralph 多轮循环会话",
)
async def create_ralph_session(
    request: CreateRalphSessionRequestDTO,
    service: RalphWorkflowService = Depends(get_ralph_workflow_service),
) -> RalphSessionResponseDTO:
    """初始化全新的 Ralph 式 Fresh-Agent 多轮循环任务。"""
    return service.create_session(request)


@router.get(
    "/sessions/{session_id}",
    response_model=RalphSessionResponseDTO,
    summary="获取 Ralph 循环会话状态与交接时间线",
)
async def get_ralph_session(
    session_id: str,
    service: RalphWorkflowService = Depends(get_ralph_workflow_service),
) -> RalphSessionResponseDTO:
    """获取指定 Ralph 循环会话的当前状态、历次五字段交接记录与下轮指令。"""
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ralph session not found: {session_id}",
        )
    return session


@router.post(
    "/sessions/{session_id}/advance-round",
    response_model=RalphSessionResponseDTO,
    summary="提交本轮五字段交接并推进至下一轮",
)
async def advance_ralph_round(
    session_id: str,
    request: AdvanceRalphRoundRequestDTO,
    service: RalphWorkflowService = Depends(get_ralph_workflow_service),
) -> RalphSessionResponseDTO:
    """
    归档本轮 Fresh 子 Agent 产物，执行容量硬顶清洗与 Min-3-Round 阻断门禁，推进至下一轮。
    """
    try:
        return service.advance_round(session_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
