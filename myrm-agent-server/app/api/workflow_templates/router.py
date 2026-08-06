"""Workflow template library HTTP API.

[INPUT]
- app.services.workflow_templates.service (POS: harness store adapter)
- app.schemas.workflow_templates (POS: REST DTOs)

[OUTPUT]
- router: /workflow-templates CRUD and save-from-run endpoints

[POS]
HTTP boundary for named Dynamic Workflow template library (vMIN).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.workflow_templates import (
    SaveWorkflowTemplateFromRunRequest,
    SaveWorkflowTemplateRequest,
    WorkflowTemplateDetailResponse,
    WorkflowTemplateListResponse,
    WorkflowTemplateSummary,
)
from app.services.workflow_templates.service import get_template_store, record_to_summary

router = APIRouter(prefix="/workflow-templates", tags=["workflow-templates"])


@router.get("", response_model=WorkflowTemplateListResponse)
async def list_workflow_templates() -> WorkflowTemplateListResponse:
    store = get_template_store()
    templates = [record_to_summary(record) for record in store.list_templates()]
    return WorkflowTemplateListResponse(templates=templates)


@router.get("/{template_id}", response_model=WorkflowTemplateDetailResponse)
async def get_workflow_template(template_id: str) -> WorkflowTemplateDetailResponse:
    store = get_template_store()
    record = store.get_template(template_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow template not found.")
    return WorkflowTemplateDetailResponse(
        template=record_to_summary(record),
        script_code=record.script_code,
    )


@router.put("/{template_id}", response_model=WorkflowTemplateSummary)
async def upsert_workflow_template(
    template_id: str,
    body: SaveWorkflowTemplateRequest,
) -> WorkflowTemplateSummary:
    store = get_template_store()
    try:
        record = store.save_template(
            template_id=template_id,
            display_name=body.display_name,
            script_code=body.script_code,
            trust_latch=body.trust_latch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record_to_summary(record)


@router.post("/from-run", response_model=WorkflowTemplateSummary)
async def save_workflow_template_from_run(
    body: SaveWorkflowTemplateFromRunRequest,
) -> WorkflowTemplateSummary:
    store = get_template_store()
    try:
        record = store.save_from_orchestration_run(
            chat_id=body.chat_id,
            message_id=body.message_id,
            template_id=body.template_id,
            display_name=body.display_name,
            trust_latch=body.trust_latch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record_to_summary(record)


@router.delete("/{template_id}")
async def delete_workflow_template(template_id: str) -> dict[str, bool]:
    store = get_template_store()
    deleted = store.delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow template not found.")
    return {"deleted": True}
