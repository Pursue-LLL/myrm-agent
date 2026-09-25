"""Trunk workflow admission gates: evidence, safety, acceptance.

[INPUT]
- handoff.TaskContextHandoff (POS: material completeness)
- harness template records + args (POS: trust and placeholder safety)
- acceptance criteria + deliverable text (POS: post-run sign-off checklist)

[OUTPUT]
- GateDecision: machine reason_code plus user-facing message (no tech jargon)
- log_admit_decision: structured observability line for run metrics

[POS]
Pure decision functions. Enforcement lives in the API admit endpoint; the DW
engine, store, and validation paths are untouched.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from myrm_agent_harness.agent.dynamic_workflow.template_store import (
    WorkflowTemplateRecord,
)
from myrm_agent_harness.agent.dynamic_workflow.template_validation import (
    validate_template_args,
)

from app.services.workflow_templates.handoff import TaskContextHandoff, validate_handoff

logger = logging.getLogger(__name__)

_WS_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class GateDecision:
    """One gate outcome: machine code plus human-readable message."""

    ok: bool
    reason_code: str
    user_message: str


def evidence_gate(handoff: TaskContextHandoff) -> GateDecision:
    """Require a complete handoff before a trunk run starts."""
    missing = validate_handoff(handoff)
    if missing:
        joined = ", ".join(missing)
        return GateDecision(
            ok=False,
            reason_code="EVIDENCE_MISSING",
            user_message=(
                f"Not enough to start yet — please add the missing pieces: {joined}. The next step needs to know what to work on."
            ),
        )
    return GateDecision(
        ok=True,
        reason_code="EVIDENCE_OK",
        user_message="Handoff is complete — ready to start.",
    )


def safety_gate(
    record: WorkflowTemplateRecord | None,
    template_args: dict[str, str] | None,
    *,
    for_cron: bool = False,
) -> GateDecision:
    """Enforce placeholder safety and the trust policy for template runs."""
    if record is None:
        return GateDecision(
            ok=False,
            reason_code="TEMPLATE_NOT_FOUND",
            user_message="That workflow no longer exists — please pick another one.",
        )
    ok, error = validate_template_args(record.script_code, template_args)
    if not ok:
        return GateDecision(
            ok=False,
            reason_code="ARGS_INVALID",
            user_message=(f"Some required details are missing or invalid. {error or 'Please fill in every field.'}"),
        )
    if for_cron and not record.trust_latch:
        return GateDecision(
            ok=False,
            reason_code="TRUST_POLICY",
            user_message=("Scheduled jobs can only use reviewed workflows. Please ask for a review first, or run it manually."),
        )
    return GateDecision(
        ok=True,
        reason_code="SAFETY_OK",
        user_message="Checks passed — safe to run.",
    )


def _normalize(text: str) -> str:
    return _WS_PATTERN.sub(" ", text.strip().lower())


def acceptance_gate(criteria: list[str], deliverable: str) -> GateDecision:
    """Check a deliverable against acceptance criteria (checklist helper)."""
    wanted = [item.strip() for item in criteria if item.strip()]
    if not wanted:
        return GateDecision(
            ok=False,
            reason_code="CRITERIA_MISSING",
            user_message="No acceptance checklist was given — nothing to verify against.",
        )
    body = _normalize(deliverable)
    unmet = [item for item in wanted if _normalize(item) not in body]
    if unmet:
        preview = "; ".join(unmet[:5])
        return GateDecision(
            ok=False,
            reason_code="CRITERIA_UNMET",
            user_message=(f"Not done yet — these checklist items are still open: {preview}."),
        )
    return GateDecision(
        ok=True,
        reason_code="ACCEPTANCE_OK",
        user_message="All checklist items are covered — ready to approve.",
    )


def log_admit_decision(
    template_id: str,
    decision: GateDecision,
    *,
    prior_checked: bool = False,
) -> None:
    """Emit a structured line so trunk admissions stay measurable."""
    logger.info(
        "[TrunkAdmit] template=%s ok=%s reason=%s prior=%s",
        template_id,
        decision.ok,
        decision.reason_code,
        prior_checked,
    )
