"""Unattended (cron) resolution of approval asks.

[INPUT]
- agent.security.command_rules::command_text (POS: The text a command-bearing tool runs: the one field of its input the tool executes.)
- agent.security.engine::check_tool_path_policy (POS: Path-zone verdict shared with the permission engine.)
- agent.security.guards.taint_tracker::TaintLabel, get_taint_tracker (POS: Session-scoped data-flow taint state.)
- agent.security.types::DEFAULT_CAPABILITIES, PermissionAction, SecurityConfig (POS: Security type hierarchy.)
- core.security.spend_governance::is_financial_or_spend_tool (POS: Foundational Agent Commerce governance module in core/security/.)
- toolkits.code_execution.security.shell_command_analyzer::is_integration_mutation_command (POS: Detects integration write mutations in shell commands.)

[OUTPUT]
- CronAskVerdict: outcome of one unattended ask (denied flag, audit reason, model-facing message)
- cron_never_class: the verdict for a call in a class no approval can cover, None for any other call
- resolve_cron_ask: decide an ask that no human can answer
- is_cron_run: whether a run belongs to a scheduled job: its config says so, or its session key has the cron prefix

[POS]
A cron run has nobody to answer an ASK, so a declared capability set stands in for the approval. Four classes of
call carry a risk no approval covers, whoever gave it (the declaration, a standing approval of the user, the
reviewer): payment-like tool calls, shell commands that write to an integration the business layer registered, web
requests sent after a credential file was read, and file paths outside the run's zones. Recognition is pattern based;
``agent/security/SECURITY_SYSTEM.md`` is the one place that spells out what each class recognizes and what it exempts.
``cron_never_class`` names them and ``resolve_cron_ask`` answers every other ask from
the declaration. Reached through ``_cron_settle``, which batch_processor calls for each ask that would wait for a
person and, at the end of a batch, for each call the allowlist or the reviewer approved.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.agent.security.command_rules import command_text
from myrm_agent_harness.agent.security.engine import check_tool_path_policy
from myrm_agent_harness.agent.security.guards.taint_tracker import TaintLabel, get_taint_tracker
from myrm_agent_harness.agent.security.types import DEFAULT_CAPABILITIES, PermissionAction, SecurityConfig
from myrm_agent_harness.core.security.spend_governance import is_financial_or_spend_tool
from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    is_integration_mutation_command,
)


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


_PAYMENT_DENIED = _denied(
    "payment-like tool call",
    "Tool denied: cron jobs cannot pre-approve payment-like tool calls, and nobody is present to approve this "
    "one. Do not retry; finish the task without this call.",
)


def cron_never_class(
    *,
    permission_type: str,
    tool_name: str,
    tool_input: dict[str, object],
    config: SecurityConfig,
    workspace_root: str | None,
) -> CronAskVerdict | None:
    """The refusal for a call in a class no approval covers, or None for any other call.

    Nobody is present to consent to these, so neither the job's declaration nor a standing approval of the user nor
    the reviewer's verdict lifts them.
    """
    # A capability names a kind of tool; it is not consent to spend, and no human is present to give that consent.
    if is_financial_or_spend_tool(tool_name, tool_input):
        return _PAYMENT_DENIED

    command = command_text(permission_type, tool_input)
    if command and is_integration_mutation_command(command):
        return _denied(
            "integration write mutation",
            "Tool denied: cron jobs cannot auto-approve Google/integration write operations.",
        )

    # Recomputed instead of read from the escalation upstream: the call reaches this point whether the engine,
    # the taint check or an approval raised it, and the reviewer may have been unavailable.
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

    return None


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

    never_class = cron_never_class(
        permission_type=permission_type,
        tool_name=tool_name,
        tool_input=tool_input,
        config=config,
        workspace_root=workspace_root,
    )
    return _PRE_APPROVED if never_class is None else never_class
