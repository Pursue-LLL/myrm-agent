"""
[POS] app/api/projects/project_state.py
[INPUT] fastapi, app.schemas.project_state, app.services.project.project_state_service
[OUTPUT] router

FastAPI router exposing ProjectState living fact ledger and context projection pipeline endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.project_state import (
    ContextProjectionRequestDTO,
    ContextProjectionResponseDTO,
    CreateLivingFactRequestDTO,
    LivingFactDTO,
    LivingFactListResponseDTO,
    ValidationAuditRequestDTO,
    ValidationAuditResponseDTO,
)
from app.services.project.project_state_service import (
    ProjectStateService,
    get_project_state_service,
)

router = APIRouter(prefix="/projects/{project_id}/state", tags=["Project State"])


@router.post(
    "/facts",
    response_model=LivingFactDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record or update a living fact in project state ledger",
)
def record_fact(
    project_id: str,
    req: CreateLivingFactRequestDTO,
    service: ProjectStateService = Depends(get_project_state_service),
) -> LivingFactDTO:
    """在项目事实状态账本中登记或更新一条决策、约束、被否决项或契约。"""
    return service.record_fact(project_id, req)


@router.get(
    "/facts",
    response_model=LivingFactListResponseDTO,
    summary="List living facts in project state ledger",
)
def list_facts(
    project_id: str,
    fact_type: str | None = Query(None, description="Filter by fact type"),
    stage: str | None = Query(None, description="Filter by promotion stage"),
    service: ProjectStateService = Depends(get_project_state_service),
) -> LivingFactListResponseDTO:
    """查询指定项目当前生效的动态事实列表，支持按类型和阶段过滤。"""
    return service.list_facts(project_id, fact_type=fact_type, stage=stage)


@router.get(
    "/facts/{fact_id}",
    response_model=LivingFactDTO,
    summary="Retrieve a single living fact by ID",
)
def get_fact(
    project_id: str,
    fact_id: str,
    service: ProjectStateService = Depends(get_project_state_service),
) -> LivingFactDTO:
    """获取指定事实项详情。"""
    fact = service.get_fact(project_id, fact_id)
    if not fact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fact '{fact_id}' not found in project '{project_id}'",
        )
    return fact


@router.delete(
    "/facts/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a living fact from project state ledger",
)
def delete_fact(
    project_id: str,
    fact_id: str,
    service: ProjectStateService = Depends(get_project_state_service),
) -> None:
    """从项目账本中移除指定事实项。"""
    success = service.delete_fact(project_id, fact_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fact '{fact_id}' not found in project '{project_id}'",
        )


@router.post(
    "/project-context",
    response_model=ContextProjectionResponseDTO,
    summary="Execute four-tier context projection pipeline",
)
def project_context(
    project_id: str,
    req: ContextProjectionRequestDTO,
    service: ProjectStateService = Depends(get_project_state_service),
) -> ContextProjectionResponseDTO:
    """根据具体任务与目标组件，执行四层级联动态上下文投影流水线。"""
    return service.project_context(project_id, req)


@router.post(
    "/audit-validation",
    response_model=ValidationAuditResponseDTO,
    summary="Audit deterministic validation outcomes and promote fact",
)
def audit_validation(
    project_id: str,
    req: ValidationAuditRequestDTO,
    service: ProjectStateService = Depends(get_project_state_service),
) -> ValidationAuditResponseDTO:
    """审计确定性测试结果，触发经验晋升阶梯或回归记录。"""
    return service.audit_validation(project_id, req)
