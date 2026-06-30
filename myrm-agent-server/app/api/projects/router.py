"""
[INPUT] services.project::ProjectService
[OUTPUT] Project CRUD REST API
[POS] 项目管理 API 路由。提供项目增删改查和会话归属管理端点。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse
from app.services.project.project_service import ProjectService

router = APIRouter()

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="项目名称")
    color: str | None = Field(None, description="项目颜色 (hex format)")


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255, description="项目名称")
    color: str | None = Field(None, description="项目颜色 (hex format)")
    workspace_path: str | None = Field(None, max_length=4096, description="项目工作目录绝对路径")


class ChatMoveRequest(BaseModel):
    projectId: str | None = Field(None, description="目标项目 ID (null=取消归属)")


class BatchMoveRequest(BaseModel):
    chatIds: list[str] = Field(..., min_length=1, description="会话 ID 列表")
    projectId: str | None = Field(None, description="目标项目 ID (null=取消归属)")


@router.get("/", response_model=StandardSuccessResponse)
async def list_projects() -> JSONResponse:
    """获取所有项目列表"""
    try:
        projects = await ProjectService.list_projects()
        return success_response(data={"projects": projects})
    except Exception as e:
        raise internal_error(operation="List projects", exception=e) from e


@router.post("/", response_model=StandardSuccessResponse)
async def create_project(req: ProjectCreateRequest) -> JSONResponse:
    """创建新项目"""
    if req.color and not _HEX_COLOR_RE.match(req.color):
        raise validation_error("Invalid color format. Must be hex (e.g. #7cb9ff)")

    try:
        project = await ProjectService.create_project(name=req.name, color=req.color)
        return success_response(data={"project": project})
    except Exception as e:
        raise internal_error(operation="Create project", exception=e) from e


@router.put("/{project_id}", response_model=StandardSuccessResponse)
async def update_project(project_id: str, req: ProjectUpdateRequest) -> JSONResponse:
    """更新项目（名称/颜色/工作目录）"""
    if req.color and not _HEX_COLOR_RE.match(req.color):
        raise validation_error("Invalid color format. Must be hex (e.g. #7cb9ff)")
    if req.workspace_path and not req.workspace_path.startswith("/"):
        raise validation_error("workspace_path must be an absolute path (starting with /)")
    if req.name is None and req.color is None and req.workspace_path is None:
        raise validation_error("At least one of name, color, or workspace_path must be provided")

    try:
        project = await ProjectService.update_project(
            project_id, name=req.name, color=req.color, workspace_path=req.workspace_path
        )
        if not project:
            raise not_found_error("Project")
        return success_response(data={"project": project})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update project", exception=e) from e


@router.delete("/{project_id}", response_model=StandardSuccessResponse)
async def delete_project(project_id: str) -> JSONResponse:
    """删除项目（会话仅取消归属，不会被删除）"""
    try:
        deleted = await ProjectService.delete_project(project_id)
        if not deleted:
            raise not_found_error("Project")
        return success_response(data={"deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Delete project", exception=e) from e


@router.patch("/chats/{chat_id}/project", response_model=StandardSuccessResponse)
async def move_chat_to_project(chat_id: str, req: ChatMoveRequest) -> JSONResponse:
    """设置/取消会话的项目归属"""
    try:
        moved = await ProjectService.move_chat_to_project(chat_id, req.projectId)
        if not moved:
            raise not_found_error("Chat or Project")
        return success_response(data={"moved": True})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Move chat to project", exception=e) from e


@router.post("/chats/batch-move", response_model=StandardSuccessResponse)
async def batch_move_chats(req: BatchMoveRequest) -> JSONResponse:
    """批量移动会话到项目"""
    try:
        count = await ProjectService.batch_move_chats(req.chatIds, req.projectId)
        return success_response(data={"movedCount": count})
    except Exception as e:
        raise internal_error(operation="Batch move chats", exception=e) from e
