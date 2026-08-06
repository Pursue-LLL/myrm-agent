"""Workflow template library service — thin wrapper over harness store.

[INPUT]
- myrm_agent_harness.agent.dynamic_workflow.paths::resolve_workflow_events_db_path (POS: workflow SQLite path SSOT)
- myrm_agent_harness.agent.dynamic_workflow.template_store::WorkflowTemplateStore (POS: template CRUD)
- app.services.context.context_assembly::ContextAssemblyService (POS: harness_path for server adapter)

[OUTPUT]
- get_template_store, record_to_summary, resolve_workflow_db_path

[POS]
Server-side adapter for workflow template persistence. Uses the same SQLite file as the DW engine.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.dynamic_workflow.paths import resolve_workflow_events_db_path
from myrm_agent_harness.agent.dynamic_workflow.template_store import (
    WorkflowTemplateRecord,
    WorkflowTemplateStore,
)
from myrm_agent_harness.agent.dynamic_workflow.template_validation import (
    extract_template_placeholders,
)

from app.schemas.workflow_templates import WorkflowTemplateSummary


def resolve_workflow_db_path() -> Path:
    from app.services.context.context_assembly import ContextAssemblyService

    facade = ContextAssemblyService.build_facade(ensure_layout=False)
    return resolve_workflow_events_db_path(harness_root=facade.harness_path())


def get_template_store() -> WorkflowTemplateStore:
    db_path = resolve_workflow_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return WorkflowTemplateStore(db_path)


def record_to_summary(record: WorkflowTemplateRecord) -> WorkflowTemplateSummary:
    return WorkflowTemplateSummary(
        template_id=record.template_id,
        display_name=record.display_name,
        script_hash=record.script_hash,
        trust_latch=record.trust_latch,
        required_agent_types=list(record.required_agent_types),
        placeholders=list(extract_template_placeholders(record.script_code)),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
