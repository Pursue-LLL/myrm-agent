"""Workflow template run validation — server adapter over harness SSOT.

[INPUT]
- myrm_agent_harness.agent.dynamic_workflow.template_validation (POS: placeholder validation SSOT)
- app.services.workflow_templates.service (POS: template store accessor)

[OUTPUT]
- validate_pinned_template_run, validate_cron_workflow_template_binding,
  validate_cron_template_at_execution

[POS]
Server-side guards for pinned Dynamic Workflow reruns and Cron template bindings.
"""

from __future__ import annotations

from myrm_agent_harness.agent.dynamic_workflow.template_store import WorkflowTemplateRecord
from myrm_agent_harness.agent.dynamic_workflow.template_validation import (
    script_all_spawns_readonly,
    validate_template_args,
)

from app.services.workflow_templates.service import get_template_store


def _validate_trusted_cron_template(
    record: WorkflowTemplateRecord | None,
    template_id: str,
    template_args: dict[str, str] | None,
    *,
    require_readonly_spawns: bool,
) -> str | None:
    if record is None:
        return f"Workflow template `{template_id}` was not found."
    if not record.trust_latch:
        return "Cron jobs may only bind trusted workflow templates (trust_latch=true)."

    ok, error = validate_template_args(record.script_code, template_args)
    if not ok:
        return error or "Invalid workflow template arguments."

    if require_readonly_spawns and not script_all_spawns_readonly(record.script_code):
        return (
            "Cron workflow template must contain only readonly spawn_subagent calls."
        )
    return None


def validate_pinned_template_run(
    template_id: str,
    template_args: dict[str, str] | None,
) -> str | None:
    """Return an error message when the pinned template run is invalid."""
    store = get_template_store()
    record = store.get_template(template_id)
    if record is None:
        return f"Workflow template `{template_id}` was not found."

    ok, error = validate_template_args(record.script_code, template_args)
    if not ok:
        return error
    return None


def validate_cron_workflow_template_binding(
    template_id: str | None,
    template_args: dict[str, str] | None,
) -> None:
    """Raise ValueError when a Cron job binds an invalid workflow template."""
    if not template_id:
        return

    store = get_template_store()
    record = store.get_template(template_id)
    error = _validate_trusted_cron_template(
        record,
        template_id,
        template_args,
        require_readonly_spawns=True,
    )
    if error:
        raise ValueError(error)


def validate_cron_template_at_execution(
    template_id: str,
    template_args: dict[str, str] | None,
) -> str | None:
    """Return an error when a Cron job must not execute this workflow template."""
    store = get_template_store()
    record = store.get_template(template_id)
    return _validate_trusted_cron_template(
        record,
        template_id,
        template_args,
        require_readonly_spawns=True,
    )
