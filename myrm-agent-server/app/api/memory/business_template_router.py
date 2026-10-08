"""router (FastAPI APIRouter for Business Scenario Experience Templates Suite).

[POS]
app/api/memory/business_template_router.py

[INPUT]
- app.schemas.business_templates, app.services.memory.business_template_service

[OUTPUT]
- router (FastAPI APIRouter for Business Scenario Experience Templates Suite)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.business_templates import (
    BusinessExperienceTemplateDTO,
    EscalationEvaluationRequest,
    EscalationEvaluationResponseDTO,
    ExportProcedureMemoriesResponseDTO,
    ListTemplatesResponseDTO,
    RecordValidationRequest,
    RecordValidationResponseDTO,
)
from app.services.memory.business_template_service import (
    BusinessTemplateService,
    get_business_template_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/business-templates", tags=["Business Scenario Templates Suite"])


@router.get(
    "/list",
    response_model=ListTemplatesResponseDTO,
    summary="List available business experience templates",
)
async def list_templates(
    service: Annotated[BusinessTemplateService, Depends(get_business_template_service)],
    category: str | None = Query(default=None, description="Optional category filter"),
    query: str | None = Query(default=None, description="Optional search keyword"),
) -> ListTemplatesResponseDTO:
    """Retrieve all business scenario experience templates with optional category filtering and search."""
    return service.list_templates(category_str=category, query=query)


@router.get(
    "/export-procedure-memories",
    response_model=ExportProcedureMemoriesResponseDTO,
    summary="Export all templates as standard procedure memory items",
)
async def export_procedure_memories(
    service: Annotated[BusinessTemplateService, Depends(get_business_template_service)],
) -> ExportProcedureMemoriesResponseDTO:
    """Export stored templates into standard ProcedureMemoryEntry items for dual-node retrieval."""
    return service.export_procedure_memories()


@router.get(
    "/{template_id}",
    response_model=BusinessExperienceTemplateDTO,
    summary="Retrieve single business experience template by ID",
)
async def get_template(
    template_id: str,
    service: Annotated[BusinessTemplateService, Depends(get_business_template_service)],
) -> BusinessExperienceTemplateDTO:
    """Retrieve specific experience template details including checklist steps and boundary conditions."""
    tpl = service.get_template(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")
    return tpl


@router.post(
    "/evaluate-escalation",
    response_model=EscalationEvaluationResponseDTO,
    summary="Evaluate operational context against human escalation gates",
)
async def evaluate_escalation(
    request: EscalationEvaluationRequest,
    service: Annotated[BusinessTemplateService, Depends(get_business_template_service)],
) -> EscalationEvaluationResponseDTO:
    """Evaluate customer or operational context to decide whether to escalate to human agent or proceed."""
    return service.evaluate_escalation(request)


@router.post(
    "/validate",
    response_model=RecordValidationResponseDTO,
    summary="Record operator or trajectory validation feedback",
)
async def record_validation(
    request: RecordValidationRequest,
    service: Annotated[BusinessTemplateService, Depends(get_business_template_service)],
) -> RecordValidationResponseDTO:
    """Record execution feedback to dynamically update template confidence and evolution counters."""
    result = service.record_validation(request)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Template not found: {request.template_id}")
    return result
