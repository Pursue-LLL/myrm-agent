"""
[INPUT] services.project.milestone_service::MilestoneService
[OUTPUT] Milestone CRUD REST API
[POS] 里程碑管理 API 路由。提供里程碑增删改查、进度查询和路线图摘要端点。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse
from app.services.project.milestone_service import MILESTONE_STATUSES, MilestoneService

router = APIRouter()


class MilestoneCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500, description="里程碑标题")
    description: str = Field("", max_length=5000, description="里程碑描述")
    acceptance_criteria: str = Field("", max_length=5000, description="验收标准")


class MilestoneUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500, description="里程碑标题")
    description: str | None = Field(None, max_length=5000, description="里程碑描述")
    acceptance_criteria: str | None = Field(None, max_length=5000, description="验收标准")
    status: str | None = Field(None, description="状态: active/completed/archived")


@router.get("/{project_id}/milestones", response_model=StandardSuccessResponse)
async def list_milestones(project_id: str, include_archived: bool = False) -> JSONResponse:
    """获取项目下的所有里程碑"""
    try:
        milestones = await MilestoneService.list_milestones(project_id, include_archived=include_archived)
        return success_response(data={"milestones": milestones})
    except Exception as e:
        raise internal_error(operation="List milestones", exception=e) from e


@router.post("/{project_id}/milestones", response_model=StandardSuccessResponse)
async def create_milestone(project_id: str, req: MilestoneCreateRequest) -> JSONResponse:
    """创建里程碑"""
    try:
        milestone = await MilestoneService.create_milestone(
            project_id,
            title=req.title,
            description=req.description,
            acceptance_criteria=req.acceptance_criteria,
        )
        return success_response(data={"milestone": milestone})
    except ValueError as e:
        raise validation_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Create milestone", exception=e) from e


@router.get("/{project_id}/milestones/{milestone_id}", response_model=StandardSuccessResponse)
async def get_milestone(project_id: str, milestone_id: str) -> JSONResponse:
    """获取单个里程碑详情"""
    try:
        milestone = await MilestoneService.get_milestone(milestone_id)
        if not milestone or milestone.get("projectId") != project_id:
            raise not_found_error("Milestone")
        return success_response(data={"milestone": milestone})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get milestone", exception=e) from e


@router.put("/{project_id}/milestones/{milestone_id}", response_model=StandardSuccessResponse)
async def update_milestone(project_id: str, milestone_id: str, req: MilestoneUpdateRequest) -> JSONResponse:
    """更新里程碑"""
    if req.status and req.status not in MILESTONE_STATUSES:
        raise validation_error(f"Invalid status. Must be one of: {', '.join(MILESTONE_STATUSES)}")
    if req.title is None and req.description is None and req.acceptance_criteria is None and req.status is None:
        raise validation_error("At least one field must be provided")

    try:
        milestone = await MilestoneService.update_milestone(
            milestone_id,
            title=req.title,
            description=req.description,
            acceptance_criteria=req.acceptance_criteria,
            status=req.status,
        )
        if not milestone or milestone.get("projectId") != project_id:
            raise not_found_error("Milestone")
        return success_response(data={"milestone": milestone})
    except ValueError as e:
        raise validation_error(str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update milestone", exception=e) from e


@router.delete("/{project_id}/milestones/{milestone_id}", response_model=StandardSuccessResponse)
async def delete_milestone(project_id: str, milestone_id: str) -> JSONResponse:
    """删除里程碑"""
    try:
        milestone = await MilestoneService.get_milestone(milestone_id)
        if not milestone or milestone.get("projectId") != project_id:
            raise not_found_error("Milestone")
        deleted = await MilestoneService.delete_milestone(milestone_id)
        if not deleted:
            raise not_found_error("Milestone")
        return success_response(data={"deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Delete milestone", exception=e) from e


@router.get("/{project_id}/milestones/{milestone_id}/progress", response_model=StandardSuccessResponse)
async def get_milestone_progress(project_id: str, milestone_id: str) -> JSONResponse:
    """获取里程碑进度统计"""
    try:
        milestone = await MilestoneService.get_milestone(milestone_id)
        if not milestone or milestone.get("projectId") != project_id:
            raise not_found_error("Milestone")
        progress = await MilestoneService.get_milestone_progress(milestone_id)
        if not progress:
            raise not_found_error("Milestone")
        return success_response(data={"progress": progress})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get milestone progress", exception=e) from e


@router.get("/{project_id}/roadmap", response_model=StandardSuccessResponse)
async def get_project_roadmap(project_id: str) -> JSONResponse:
    """获取项目路线图摘要（含所有活跃里程碑和进度）"""
    try:
        roadmap = await MilestoneService.get_project_roadmap_summary(project_id)
        if not roadmap:
            raise not_found_error("Project")
        return success_response(data={"roadmap": roadmap})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get project roadmap", exception=e) from e
