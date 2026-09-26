"""Workflow template library HTTP API.

[INPUT]
- app.services.workflow_templates.service (POS: harness store adapter)
- app.schemas.workflow_templates (POS: REST DTOs)

[OUTPUT]
- router: /workflow-templates CRUD, save-from-run, and admit-gate endpoints

[POS]
HTTP boundary for named Dynamic Workflow template library (vMIN).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.workflow_templates import (
    AdmitTemplateRunRequest,
    AdmitTemplateRunResponse,
    SaveWorkflowTemplateFromRunRequest,
    SaveWorkflowTemplateRequest,
    WorkflowTemplateDetailResponse,
    WorkflowTemplateListResponse,
    WorkflowTemplateSummary,
)
from app.services.workflow_templates.cron_binding import count_cron_jobs_bound_to_template
from app.services.workflow_templates.service import get_template_store, record_to_summary

router = APIRouter(prefix="/workflow-templates", tags=["workflow-templates"])


@router.get("", response_model=WorkflowTemplateListResponse)
async def list_workflow_templates() -> WorkflowTemplateListResponse:
    store = get_template_store()
    templates = [record_to_summary(record) for record in store.list_templates()]
    return WorkflowTemplateListResponse(templates=templates)


@router.get("/trunk-catalog")
async def get_trunk_catalog() -> dict[str, object]:
    """Serve prebuilt trunk catalog metadata (no script bodies)."""
    from app.services.workflow_templates.trunk_templates import (
        TRUNK_CATALOG_VERSION,
        describe_trunk_catalog,
    )

    return {"version": TRUNK_CATALOG_VERSION, "templates": describe_trunk_catalog()}


@router.get("/{template_id}", response_model=WorkflowTemplateDetailResponse)
async def get_workflow_template(template_id: str) -> WorkflowTemplateDetailResponse:
    store = get_template_store()
    record = store.get_template(template_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow template not found.")
    bound_cron_count = await count_cron_jobs_bound_to_template(template_id)
    return WorkflowTemplateDetailResponse(
        template=record_to_summary(record),
        script_code=record.script_code,
        bound_cron_count=bound_cron_count,
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


@router.post("/{template_id}/admit", response_model=AdmitTemplateRunResponse)
async def admit_template_run(template_id: str, body: AdmitTemplateRunRequest) -> AdmitTemplateRunResponse:
    """Run trunk admission gates (evidence, safety, prior acceptance)."""
    from app.services.workflow_templates.gates import (
        GateDecision,
        acceptance_gate,
        evidence_gate,
        log_admit_decision,
        safety_gate,
    )
    from app.services.workflow_templates.handoff import build_handoff, to_template_args

    store = get_template_store()
    record = store.get_template(template_id)

    merged_args: dict[str, str] = dict(body.template_args or {})
    if body.handoff is not None:
        handoff = build_handoff(
            source_flow=body.handoff.source_flow,
            target_flow=body.handoff.target_flow,
            intent=body.handoff.intent,
            materials=[(item.title, item.excerpt) for item in body.handoff.materials],
            evidence_refs=list(body.handoff.evidence_refs),
        )
        decision = evidence_gate(handoff)
        if not decision.ok:
            log_admit_decision(template_id, decision)
            raise HTTPException(status_code=422, detail={"reason_code": decision.reason_code, "message": decision.user_message})
        for key, value in to_template_args(handoff).items():
            merged_args.setdefault(key, value)

    decision = safety_gate(record, merged_args)
    if not decision.ok:
        log_admit_decision(template_id, decision)
        raise HTTPException(status_code=422, detail={"reason_code": decision.reason_code, "message": decision.user_message})

    prior_checked = body.prior_criteria is not None
    if prior_checked:
        decision = acceptance_gate(list(body.prior_criteria or []), body.prior_deliverable or "")
        if not decision.ok:
            log_admit_decision(template_id, decision, prior_checked=True)
            raise HTTPException(status_code=422, detail={"reason_code": decision.reason_code, "message": decision.user_message})

    admitted = AdmitTemplateRunResponse(
        admitted=True,
        template_id=template_id,
        reason_code="ADMITTED",
        user_message="Ready — starting the workflow.",
    )
    log_admit_decision(
        template_id,
        GateDecision(ok=True, reason_code="ADMITTED", user_message=admitted.user_message),
    )
    return admitted
