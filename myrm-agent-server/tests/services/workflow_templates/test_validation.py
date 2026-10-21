"""Workflow template execution guards for Cron runs."""

from __future__ import annotations

from myrm_agent_harness.agent.dynamic_workflow.template_store import WorkflowTemplateStore

from app.services.workflow_templates.validation import validate_cron_template_at_execution

_READONLY_SCRIPT = """
import myrm_tools
myrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="hello", readonly=True)
"""

_SCRIPT_WITH_PLACEHOLDER = """
import myrm_tools
myrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="{topic}", readonly=True)
"""

_NON_READONLY_SCRIPT = """
import myrm_tools
myrm_tools.spawn_subagent(task_id="t1", agent_type="generalPurpose", task_description="hello")
"""


def test_execution_guard_accepts_trusted_readonly_template(tmp_path) -> None:
    db_path = tmp_path / "workflow.db"
    store = WorkflowTemplateStore(db_path)
    store.save_template(
        template_id="trusted-flow",
        display_name="Trusted Flow",
        script_code=_SCRIPT_WITH_PLACEHOLDER,
        trust_latch=True,
    )

    from app.services.workflow_templates import service as workflow_templates_service

    original = workflow_templates_service.resolve_workflow_db_path
    workflow_templates_service.resolve_workflow_db_path = lambda: db_path
    try:
        error = validate_cron_template_at_execution(
            "trusted-flow",
            {"topic": "billing"},
        )
    finally:
        workflow_templates_service.resolve_workflow_db_path = original

    assert error is None


def test_execution_guard_rejects_mutated_non_readonly_template(tmp_path) -> None:
    db_path = tmp_path / "workflow.db"
    store = WorkflowTemplateStore(db_path)
    store.save_template(
        template_id="trusted-flow",
        display_name="Trusted Flow",
        script_code=_SCRIPT_WITH_PLACEHOLDER,
        trust_latch=True,
    )
    store.save_template(
        template_id="trusted-flow",
        display_name="Trusted Flow",
        script_code=_NON_READONLY_SCRIPT,
        trust_latch=True,
    )

    from app.services.workflow_templates import service as workflow_templates_service

    original = workflow_templates_service.resolve_workflow_db_path
    workflow_templates_service.resolve_workflow_db_path = lambda: db_path
    try:
        error = validate_cron_template_at_execution(
            "trusted-flow",
            {"topic": "billing"},
        )
    finally:
        workflow_templates_service.resolve_workflow_db_path = original

    assert error is not None
    assert "readonly" in error


def test_execution_guard_rejects_missing_args(tmp_path) -> None:
    db_path = tmp_path / "workflow.db"
    store = WorkflowTemplateStore(db_path)
    store.save_template(
        template_id="trusted-flow",
        display_name="Trusted Flow",
        script_code=_SCRIPT_WITH_PLACEHOLDER,
        trust_latch=True,
    )

    from app.services.workflow_templates import service as workflow_templates_service

    original = workflow_templates_service.resolve_workflow_db_path
    workflow_templates_service.resolve_workflow_db_path = lambda: db_path
    try:
        error = validate_cron_template_at_execution("trusted-flow", None)
    finally:
        workflow_templates_service.resolve_workflow_db_path = original

    assert error is not None
    assert "topic" in error


def test_execution_guard_rejects_readonly_string_bypass(tmp_path) -> None:
    db_path = tmp_path / "workflow.db"
    store = WorkflowTemplateStore(db_path)
    bypass_script = """
import myrm_tools
myrm_tools.spawn_subagent(
    task_id="t1",
    agent_type="generalPurpose",
    task_description="summarize readonly=True news",
)
"""
    store.save_template(
        template_id="trusted-flow",
        display_name="Trusted Flow",
        script_code=bypass_script,
        trust_latch=True,
    )

    from app.services.workflow_templates import service as workflow_templates_service

    original = workflow_templates_service.resolve_workflow_db_path
    workflow_templates_service.resolve_workflow_db_path = lambda: db_path
    try:
        error = validate_cron_template_at_execution("trusted-flow", None)
    finally:
        workflow_templates_service.resolve_workflow_db_path = original

    assert error is not None
    assert "readonly" in error


def test_execution_guard_rejects_untrusted_template(tmp_path) -> None:
    db_path = tmp_path / "workflow.db"
    store = WorkflowTemplateStore(db_path)
    store.save_template(
        template_id="trusted-flow",
        display_name="Trusted Flow",
        script_code=_READONLY_SCRIPT,
        trust_latch=False,
    )

    from app.services.workflow_templates import service as workflow_templates_service

    original = workflow_templates_service.resolve_workflow_db_path
    workflow_templates_service.resolve_workflow_db_path = lambda: db_path
    try:
        error = validate_cron_template_at_execution("trusted-flow", None)
    finally:
        workflow_templates_service.resolve_workflow_db_path = original

    assert error is not None
    assert "trust_latch" in error
