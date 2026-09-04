# [INPUT] app.services.browser_spaces::get_task_space_service (POS: 任务空间服务单例获取)
# [INPUT] app.services.browser_spaces::TaskSpaceInfo (POS: 任务空间信息模型)
# [OUTPUT] router: APIRouter (POS: 浏览器任务空间路由入口)
# [POS] 浏览器任务空间 REST API 控制器。暴露多空间列表、创建、销毁、接管与过期清理端点。

"""Browser Task Spaces REST API endpoints for WebUI and Subagent orchestration."""

from __future__ import annotations

import logging
from typing import Literal

from app.services.browser_spaces import (
    TaskSpaceInfo,
    get_task_space_service,
)
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateSpaceRequest(BaseModel):
    space_id: str = Field(..., min_length=1, max_length=64, description="Unique workspace identifier")
    name: str | None = Field(None, max_length=128, description="Human-readable title")
    chat_id: str | None = Field(None, max_length=64, description="Associated chat session ID")


class TakeoverRequest(BaseModel):
    enabled: bool = Field(..., description="Whether human takeover is active")


class PruneResponse(BaseModel):
    pruned_count: int


@router.get("/spaces", response_model=list[TaskSpaceInfo])
async def list_task_spaces() -> list[TaskSpaceInfo]:
    """List all currently active browser task spaces."""
    service = get_task_space_service()
    return await service.list_spaces()


@router.post("/spaces", response_model=TaskSpaceInfo)
async def create_or_get_task_space(request: CreateSpaceRequest) -> TaskSpaceInfo:
    """Allocate a new isolated task space or retrieve existing under quota limits."""
    service = get_task_space_service()
    try:
        return await service.get_or_create_space(
            space_id=request.space_id,
            name=request.name,
            chat_id=request.chat_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.delete("/spaces/{space_id}")
async def close_task_space(space_id: str) -> dict[str, object]:
    """Gracefully close and release a task space."""
    service = get_task_space_service()
    closed = await service.close_space(space_id)
    if not closed:
        raise HTTPException(status_code=404, detail=f"TaskSpace '{space_id}' not found")
    return {"success": True, "closed_space_id": space_id}


@router.post("/spaces/{space_id}/takeover", response_model=TaskSpaceInfo)
async def toggle_task_space_takeover(
    space_id: str,
    request: TakeoverRequest,
) -> TaskSpaceInfo:
    """Toggle human-takeover mode for the given space."""
    service = get_task_space_service()
    try:
        return await service.set_takeover(space_id=space_id, enabled=request.enabled)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/spaces/{space_id}/snapshot")
async def get_task_space_snapshot(space_id: str) -> dict[str, object]:
    """Capture a live screenshot and URL metadata for the given task space."""
    service = get_task_space_service()
    try:
        return await service.get_space_snapshot(space_id=space_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/spaces/prune", response_model=PruneResponse)
async def prune_idle_task_spaces(
    max_idle_seconds: float = Query(900.0, ge=10.0, description="Eviction TTL threshold in seconds"),
) -> PruneResponse:
    """Manually trigger eviction of idle task spaces exceeding TTL."""
    service = get_task_space_service()
    count = await service.prune_idle(max_idle_seconds=max_idle_seconds)
    return PruneResponse(pruned_count=count)
