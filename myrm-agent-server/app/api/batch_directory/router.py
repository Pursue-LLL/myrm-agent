"""BatchDirectory REST API.

[INPUT]
- app.services.batch_directory::BatchDirectoryService (POS: 批量项目编排)
- app.api.batch_directory.schemas (POS: 请求/响应模型)

[OUTPUT]
- router: BatchDirectory CRUD/cancel 端点

[POS]
BatchDirectory HTTP 层。负责请求校验、错误映射和 service 调用装配，
不承载业务编排。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.batch_directory.schemas import (
    BatchProjectCreate,
    BatchProjectDetailResponse,
    BatchProjectListResponse,
    BatchProjectResponse,
)
from app.services.batch_directory import BatchDirectoryService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/batch-directories", tags=["batch-directories"])


def _svc() -> BatchDirectoryService:
    return BatchDirectoryService.get_instance()


@router.post("", response_model=BatchProjectDetailResponse, status_code=201)
async def create_project(body: BatchProjectCreate) -> BatchProjectDetailResponse:
    try:
        result = await _svc().create_project(
            name=body.name,
            prompt=body.prompt,
            directories=body.directories,
            board_id=body.board_id,
            concurrency=body.concurrency,
            agent_id=body.agent_id,
            model_override=body.model_override,
            max_runtime_seconds=body.max_runtime_seconds,
            require_approval=body.require_approval,
            notify_enabled=body.notify_enabled,
            artifact_patterns=body.artifact_patterns,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return BatchProjectDetailResponse(**result)


@router.get("", response_model=BatchProjectListResponse)
async def list_projects() -> BatchProjectListResponse:
    items = await _svc().list_projects()
    return BatchProjectListResponse(
        items=[BatchProjectResponse(**item) for item in items],
        total=len(items),
    )


@router.get("/{project_id}", response_model=BatchProjectDetailResponse)
async def get_project(project_id: str) -> BatchProjectDetailResponse:
    result = await _svc().get_project(project_id)
    if result is None:
        raise HTTPException(404, f"Batch project {project_id} not found")
    return BatchProjectDetailResponse(**result)


@router.post("/{project_id}/cancel", response_model=BatchProjectDetailResponse)
async def cancel_project(project_id: str) -> BatchProjectDetailResponse:
    result = await _svc().cancel_project(project_id)
    if result is None:
        raise HTTPException(404, f"Batch project {project_id} not found")
    return BatchProjectDetailResponse(**result)


@router.post("/{project_id}/retry", response_model=BatchProjectDetailResponse)
async def retry_failed(project_id: str) -> BatchProjectDetailResponse:
    try:
        result = await _svc().retry_failed(project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, f"Batch project {project_id} not found")
    return BatchProjectDetailResponse(**result)


@router.post("/{project_id}/rerun", response_model=BatchProjectDetailResponse)
async def rerun_project(project_id: str) -> BatchProjectDetailResponse:
    try:
        result = await _svc().rerun_project(project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, f"Batch project {project_id} not found")
    return BatchProjectDetailResponse(**result)


@router.post(
    "/{project_id}/tasks/{task_id}/retry",
    response_model=BatchProjectDetailResponse,
)
async def retry_task(project_id: str, task_id: str) -> BatchProjectDetailResponse:
    try:
        result = await _svc().retry_task(project_id, task_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, f"Batch project {project_id} not found")
    return BatchProjectDetailResponse(**result)


@router.post("/{project_id}/pause", response_model=BatchProjectDetailResponse)
async def pause_project(project_id: str) -> BatchProjectDetailResponse:
    try:
        result = await _svc().pause_project(project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, f"Batch project {project_id} not found")
    return BatchProjectDetailResponse(**result)


@router.post("/{project_id}/resume", response_model=BatchProjectDetailResponse)
async def resume_project(project_id: str) -> BatchProjectDetailResponse:
    try:
        result = await _svc().resume_project(project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, f"Batch project {project_id} not found")
    return BatchProjectDetailResponse(**result)


@router.post("/{project_id}/approve-all", response_model=BatchProjectDetailResponse)
async def approve_all_results(project_id: str) -> BatchProjectDetailResponse:
    try:
        result = await _svc().approve_all_results(project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, f"Batch project {project_id} not found")
    return BatchProjectDetailResponse(**result)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str) -> None:
    try:
        deleted = await _svc().delete_project(project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, f"Batch project {project_id} not found")
