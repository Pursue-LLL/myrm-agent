"""
[INPUT] services.project.milestone_service::MilestoneService
[OUTPUT] Milestone CRUD REST API + assessment import endpoint
[POS] 里程碑管理 API 路由。提供里程碑增删改查、进度查询、路线图摘要，以及评估工件导入与结构化错误语义返回。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import (
    conflict_error,
    internal_error,
    not_found_error,
    unprocessable_error,
    validation_error,
)
from app.core.utils.response_utils import success_response
from app.database.standard_responses import ErrorDetail, StandardSuccessResponse
from app.services.project.assessment_import_service import (
    ERROR_ARTIFACT_VERSION_ALREADY_IMPORTED,
    ERROR_NO_ACTIONABLE_TASKS,
    ERROR_NO_IMPORTABLE_TASKS,
    AssessmentImportService,
)
from app.services.project.milestone_service import MILESTONE_STATUSES, MilestoneService

router = APIRouter()

IMPORT_REASON_FIELD = "import_reason"
IMPORT_REASON_ARTIFACT_VERSION_ALREADY_IMPORTED = "artifact_version_already_imported"
IMPORT_REASON_NO_ACTIONABLE_TASKS = "no_actionable_tasks"
IMPORT_REASON_NO_IMPORTABLE_TASKS = "no_importable_tasks"
IMPORT_REASON_ARTIFACT_NOT_FOUND = "artifact_not_found"
IMPORT_REASON_PROJECT_NOT_FOUND = "project_not_found"


def _import_reason_details(issue: str) -> list[ErrorDetail]:
    return [ErrorDetail(field=IMPORT_REASON_FIELD, issue=issue)]


class MilestoneCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500, description="里程碑标题")
    description: str = Field("", max_length=5000, description="里程碑描述")
    acceptance_criteria: str = Field("", max_length=5000, description="验收标准")


class MilestoneUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500, description="里程碑标题")
    description: str | None = Field(None, max_length=5000, description="里程碑描述")
    acceptance_criteria: str | None = Field(None, max_length=5000, description="验收标准")
    status: str | None = Field(None, description="状态: active/completed/archived")


class AssessmentImportRequest(BaseModel):
    artifact_id: str = Field(..., min_length=1, description="Source artifact id")
    source_chat_id: str | None = Field(None, min_length=1, description="Optional source chat id for task metadata")
    max_milestones: int = Field(8, ge=1, le=20, description="Max milestones parsed from artifact")
    max_tasks_per_milestone: int = Field(25, ge=1, le=100, description="Max imported tasks per milestone")


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


@router.get("/{project_id}/milestones/batch-progress", response_model=StandardSuccessResponse)
async def get_batch_progress(project_id: str) -> JSONResponse:
    """批量获取项目下所有活跃里程碑的进度统计"""
    try:
        progress_list = await MilestoneService.get_batch_progress(project_id)
        return success_response(data={"progress": progress_list})
    except Exception as e:
        raise internal_error(operation="Get batch milestone progress", exception=e) from e


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


@router.post("/{project_id}/milestones/import-assessment", response_model=StandardSuccessResponse)
async def import_assessment(project_id: str, req: AssessmentImportRequest) -> JSONResponse:
    """Import assessment artifact into project milestones and kanban tasks."""
    try:
        receipt = await AssessmentImportService.import_from_artifact(
            project_id,
            artifact_id=req.artifact_id,
            source_chat_id=req.source_chat_id,
            max_milestones=req.max_milestones,
            max_tasks_per_milestone=req.max_tasks_per_milestone,
        )
        return success_response(data={"receipt": receipt})
    except FileNotFoundError as exc:
        detail = str(exc).lower()
        if "project" in detail:
            raise not_found_error(
                "Project",
                details=_import_reason_details(IMPORT_REASON_PROJECT_NOT_FOUND),
            ) from exc
        raise not_found_error(
            "Artifact",
            details=_import_reason_details(IMPORT_REASON_ARTIFACT_NOT_FOUND),
        ) from exc
    except ValueError as exc:
        detail = str(exc).strip()
        if detail == ERROR_ARTIFACT_VERSION_ALREADY_IMPORTED:
            raise conflict_error(
                detail,
                details=_import_reason_details(IMPORT_REASON_ARTIFACT_VERSION_ALREADY_IMPORTED),
            ) from exc
        if detail in {ERROR_NO_ACTIONABLE_TASKS, ERROR_NO_IMPORTABLE_TASKS}:
            issue = (
                IMPORT_REASON_NO_ACTIONABLE_TASKS
                if detail == ERROR_NO_ACTIONABLE_TASKS
                else IMPORT_REASON_NO_IMPORTABLE_TASKS
            )
            raise unprocessable_error(detail, details=_import_reason_details(issue)) from exc
        raise validation_error(detail) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(operation="Import assessment artifact", exception=exc) from exc
