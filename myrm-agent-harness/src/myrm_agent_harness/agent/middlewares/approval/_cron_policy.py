"""Unattended (cron) resolution of approval asks.

[INPUT]
- agent.security.engine::check_tool_path_policy (POS: Path-zone verdict shared with the permission engine.)
- agent.security.guards.taint_tracker::TaintLabel, get_taint_tracker (POS: Session-scoped data-flow taint state.)
- agent.security.types::DEFAULT_CAPABILITIES, PermissionAction, SecurityConfig (POS: Security type hierarchy.)
- core.security.spend_governance::is_financial_or_spend_tool (POS: Foundational Agent Commerce governance module in core/security/.)
- toolkits.code_execution.security.shell_command_analyzer::is_integration_mutation_command (POS: Detects integration write mutations in shell commands.)

[OUTPUT]
- CronAskVerdict: outcome of one unattended ask (denied flag, audit reason, model-facing message)
- PAYMENT_DENIED: the verdict for a payment-like tool call in a run nobody can approve
- resolve_cron_ask: decide an ask that no human can answer
- is_cron_run: whether a run belongs to a scheduled job: its config says so, or its session key has the cron prefix

[POS]
A cron run has nobody to answer an ASK, so a declared capability set stands in for the approval,
except for asks that carry a risk the declaration does not cover: credential data leaving the
session, writes outside the job's directories, integration write mutations, payment-like tool
calls. Reached through ``_cron_settle``, which batch_processor calls after the allowlist and the
optional LLM review had their say, and again at the end of a batch for every call that would
otherwise wait: the asks a YOLO switch leaves open (it answers none in a scheduled run), a review that
could not decide, the agents the job delegated to. The YOLO branch refuses a payment-like call itself
with PAYMENT_DENIED, ahead of that settlement.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.agent.security.engine import check_tool_path_policy
from myrm_agent_harness.agent.security.guards.taint_tracker import TaintLabel, get_taint_tracker
from myrm_agent_harness.agent.security.types import DEFAULT_CAPABILITIES, PermissionAction, SecurityConfig
from myrm_agent_harness.core.security.spend_governance import is_financial_or_spend_tool
from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    is_integration_mutation_command,
)

_SHELL_PERMISSIONS = frozenset({"shell_exec", "code_interpreter"})


@dataclass(frozen=True, slots=True)
class CronAskVerdict:
    """Outcome of one ask in an unattended run."""

    denied: bool
    audit_reason: str
    tool_message: str = ""


_PRE_APPROVED = CronAskVerdict(denied=False, audit_reason="cron capability pre-approval")


def is_cron_run(config: SecurityConfig | None, session_key: str) -> bool:
    """Whether this run belongs to a scheduled job: its config says so, or its session key has the ``cron:`` prefix."""
    return bool(config and config.is_cron) or session_key.startswith("cron:")


def _denied(audit_reason: str, tool_message: str) -> CronAskVerdict:
    return CronAskVerdict(denied=True, audit_reason=f"cron fail-closed: {audit_reason}", tool_message=tool_message)


PAYMENT_DENIED = _denied(
    "payment-like tool call",
    "Tool denied: cron jobs cannot pre-approve payment-like tool calls, and nobody is present to approve this "
    "one. Do not retry; finish the task without this call.",
)


def resolve_cron_ask(
    *,
    permission_type: str,
    tool_name: str,
    tool_input: dict[str, object],
    config: SecurityConfig,
    workspace_root: str | None,
) -> CronAskVerdict:
    """Pre-approve the ask through the job's declared capabilities, or deny it fail-closed."""
    if config.capabilities == DEFAULT_CAPABILITIES:
        return _denied(
            "no explicit capability declaration",
            "Tool denied: cron fail-closed policy. This cron job has no explicit capability declaration.",
        )

    # A capability names a kind of tool; it is not consent to spend, and no human is present to give that consent.
    if is_financial_or_spend_tool(tool_name, tool_input):
        return PAYMENT_DENIED

    if permission_type in _SHELL_PERMISSIONS:
        command = str(tool_input.get("command", "") or tool_input.get("code", "") or tool_input.get("data", "")).strip()
        if command and is_integration_mutation_command(command):
            return _denied(
                "integration write mutation",
                "Tool denied: cron jobs cannot auto-approve Google/integration write operations.",
            )

    # Recomputed instead of read from the escalation upstream: the same ask reaches this point
    # whether the engine or the taint check raised it, and the reviewer may have been unavailable.
    egress_conflict = get_taint_tracker().check_sink(
        tool_name, tool_input=tool_input, trusted_hosts=config.network_allowlist
    )
    if egress_conflict and TaintLabel.SECRET in egress_conflict:
        return _denied(
            "network egress after credential read",
            "Tool denied: this cron job read credential data earlier in the run, so sending data out is blocked. "
            "Do not retry; finish the task without this call.",
        )

    path_verdict = check_tool_path_policy(permission_type, tool_input, config, workspace_root)
    if path_verdict is not None and path_verdict[0] != PermissionAction.ALLOW:
        path_reason = path_verdict[1]
        return _denied(
            path_reason,
            f"Tool denied: {path_reason}. A cron job cannot ask for approval; skip this step or choose another path.",
        )

    return _PRE_APPROVED
