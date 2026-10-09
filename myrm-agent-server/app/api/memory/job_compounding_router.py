"""[POS]: app/api/memory/job_compounding_router.py
[INPUT]: FastAPI APIRouter, Depends, Query, Path, HTTPException, and job compounding schemas.
[OUTPUT]: API router exposing endpoints for agent job descriptions, approval gates, and compounded experience.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.job_compounding import (
    CheckApprovalRequestDTO,
    CheckApprovalResponseDTO,
    CompoundedRuleDTO,
    CompoundingMaturityReportDTO,
    JobDescriptionSpecDTO,
    RecordRuleRequestDTO,
    SaveJobDescriptionRequestDTO,
)
from app.services.memory.job_compounding_service import (
    DomainJobCompoundingService,
    get_job_compounding_service,
)

router = APIRouter(prefix="/job-compounding", tags=["memory-job-compounding"])


@router.post("/jobs", response_model=JobDescriptionSpecDTO)
async def save_job_description(
    request: SaveJobDescriptionRequestDTO,
    service: DomainJobCompoundingService = Depends(get_job_compounding_service),
) -> JobDescriptionSpecDTO:
    """Creates or updates a domain-specific agent job description."""
    return service.save_job_description(request)


@router.get("/jobs/{agent_id}", response_model=JobDescriptionSpecDTO)
async def get_job_description(
    agent_id: str,
    service: DomainJobCompoundingService = Depends(get_job_compounding_service),
) -> JobDescriptionSpecDTO:
    """Retrieves the active 4-pillar job description for an agent."""
    spec = service.get_job_description(agent_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Job description for agent '{agent_id}' not found")
    return spec


@router.post("/approval/check", response_model=CheckApprovalResponseDTO)
async def check_approval_boundary(
    request: CheckApprovalRequestDTO,
    service: DomainJobCompoundingService = Depends(get_job_compounding_service),
) -> CheckApprovalResponseDTO:
    """Evaluates whether a planned action requires human approval."""
    return service.check_approval_boundary(request)


@router.post("/rules", response_model=CompoundedRuleDTO)
async def record_compounded_rule(
    request: RecordRuleRequestDTO,
    service: DomainJobCompoundingService = Depends(get_job_compounding_service),
) -> CompoundedRuleDTO:
    """Appends a new compounded domain rule from execution feedback."""
    return service.record_compounded_rule(request)


@router.get("/rules/{agent_id}", response_model=list[CompoundedRuleDTO])
async def list_compounded_rules(
    agent_id: str,
    rule_type: str | None = Query(default=None, description="Optional rule type filter"),
    service: DomainJobCompoundingService = Depends(get_job_compounding_service),
) -> list[CompoundedRuleDTO]:
    """Lists all compounded rules accumulated by an agent."""
    return service.list_compounded_rules(agent_id=agent_id, rule_type=rule_type)


@router.get("/maturity/{agent_id}", response_model=CompoundingMaturityReportDTO)
async def evaluate_maturity(
    agent_id: str,
    service: DomainJobCompoundingService = Depends(get_job_compounding_service),
) -> CompoundingMaturityReportDTO:
    """Evaluates the compounding maturity score and tier of an agent."""
    return service.evaluate_maturity(agent_id)
