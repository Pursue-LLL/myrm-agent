"""
[INPUT]
- app.schemas.subagent_hub.*
- app.services.agent.subagent_hub_service.SubagentHubService
- fastapi (APIRouter, Depends, Path, Query)

[OUTPUT]
- router (Subagent Hub API Router)
- GET /chats/{chat_id}/subagents/hub/roster
- GET /chats/{chat_id}/subagents/{task_id}/transcript
- POST /chats/{chat_id}/subagents/{task_id}/action

[POS]
Server 业务层子代理实时监管抽屉 REST 路由（Topic 12 · 第 18 项）。
对齐 oh-my-pi Agent Hub 架构，提供 roster 概览、live transcript 读取与 steer/kill/revive 动作调度。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from app.core.utils.response_utils import error_response, success_response
from app.schemas.subagent_hub import (
    SubagentRosterOverviewResponseDTO,
    SubagentTranscriptResponseDTO,
    SupervisionActionRequestDTO,
    SupervisionActionResponseDTO,
)
from app.services.agent.subagent_hub_service import SubagentHubService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/subagents", tags=["Subagent Supervision Hub"])

_subagent_hub_service_instance: SubagentHubService | None = None


def get_subagent_hub_service() -> SubagentHubService:
    """Dependency injector for SubagentHubService."""
    global _subagent_hub_service_instance
    if _subagent_hub_service_instance is None:
        _subagent_hub_service_instance = SubagentHubService()
    return _subagent_hub_service_instance


@router.get("/hub/roster", response_model=SubagentRosterOverviewResponseDTO)
async def get_session_roster_overview(
    chat_id: Annotated[str, Path(..., description="The parent chat session ID")],
    service: Annotated[SubagentHubService, Depends(get_subagent_hub_service)],
) -> JSONResponse:
    """Fetch live supervision roster overview and metrics for all subagents in a session."""
    try:
        overview = await service.get_roster_overview(chat_id)
        return success_response(data=overview.model_dump())
    except Exception as exc:
        logger.exception("Failed to fetch subagent roster overview for %s", chat_id)
        return error_response(
            message=f"Failed to fetch subagent roster: {exc}",
            status_code=500,
        )


@router.get("/{task_id}/transcript", response_model=SubagentTranscriptResponseDTO)
async def get_subagent_live_transcript(
    chat_id: Annotated[str, Path(..., description="The parent chat session ID")],
    task_id: Annotated[str, Path(..., description="The target subagent task ID")],
    limit: Annotated[
        int | None, Query(description="Maximum transcript entries to retrieve", ge=1, le=200)
    ] = 100,
    service: Annotated[SubagentHubService, Depends(get_subagent_hub_service)] = None,
) -> JSONResponse:
    """Fetch execution transcript entries for a target subagent worker."""
    if service is None:
        service = get_subagent_hub_service()
    try:
        transcript = service.get_transcript(chat_id, task_id, limit=limit)
        return success_response(data=transcript.model_dump())
    except Exception as exc:
        logger.exception("Failed to fetch transcript for subagent %s", task_id)
        return error_response(
            message=f"Failed to fetch transcript: {exc}",
            status_code=500,
        )


@router.post("/{task_id}/action", response_model=SupervisionActionResponseDTO)
async def execute_subagent_supervision_action(
    chat_id: Annotated[str, Path(..., description="The parent chat session ID")],
    task_id: Annotated[str, Path(..., description="The target subagent task ID")],
    req: SupervisionActionRequestDTO,
    service: Annotated[SubagentHubService, Depends(get_subagent_hub_service)],
) -> JSONResponse:
    """Dispatch a supervision action (steer, kill, revive) to a target worker."""
    try:
        res = service.execute_action(
            chat_id=chat_id,
            task_id=task_id,
            action=req.action,
            message=req.message,
        )
        if not res.success:
            return error_response(
                message=res.message,
                status_code=400,
            )
        return success_response(data=res.model_dump())
    except Exception as exc:
        logger.exception("Failed to execute supervision action %s on %s", req.action, task_id)
        return error_response(
            message=f"Failed to execute supervision action: {exc}",
            status_code=500,
        )
