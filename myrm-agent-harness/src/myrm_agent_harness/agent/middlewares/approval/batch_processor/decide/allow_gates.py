"""[INPUT]
- myrm_agent_harness.agent.security.audit::record_decision (POS: Security audit log — re-exported from core.security.audit.)
- myrm_agent_harness.agent.security.types::PermissionAction (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.core.security.spend_governance::is_financial_or_spend_tool / is_irreversible_social_action (POS: Foundational Agent Commerce governance module in core/security/.)
- myrm_agent_harness.toolkits.code_execution.security.ast_parser::is_destructive_shell_tool_call (POS: Shell execution security: AST semantic parsing and capability boundary gating.)
- myrm_agent_harness.agent.middlewares.approval.helpers::ThresholdBreach / is_threshold_breached (POS: Approval middleware helper functions. Implements dual-threshold denial tracking (consecutive + total) with proactive guidance on every denial and automatic consecutive counter reset on any allowed operation.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor._workspace_snapshot::pre_destructive_snapshot_id (POS: A destructive command waits for the user's approval with a rollback point; the decision loop and the YOLO branch both take it through this helper.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- regate_allowed: send an ALLOW back to ASK when a gate no allow source may lift applies

[POS]
Fourth decision stage. An ALLOW can come from the engine, a read-only fast path or the allowlist; none of them may lift
a socially irreversible action, a financial spend or an irreversible destructive shell command, and none may outlast a
breached denial threshold in auto mode.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.types import PermissionAction
from myrm_agent_harness.core.security.spend_governance import (
    is_financial_or_spend_tool,
    is_irreversible_social_action,
)
from myrm_agent_harness.toolkits.code_execution.security.ast_parser import (
    is_destructive_shell_tool_call,
)

from ...helpers import ThresholdBreach, is_threshold_breached
from .._workspace_snapshot import pre_destructive_snapshot_id
from .state import BatchContext, CallState


def regate_allowed(ctx: BatchContext, call: CallState) -> None:
    """Escalate an ALLOW to ASK when a gate that no allow source may lift applies."""
    tool_name, tool_input = call.tool_name, call.tool_input

    if call.action == PermissionAction.ALLOW and is_irreversible_social_action(tool_name, tool_input):
        call.action = PermissionAction.ASK
        call.reason = f"Socially irreversible operation ({tool_name}) requires explicit human approval"
        extra_ctx = call.context()
        extra_ctx["socially_irreversible"] = True
        extra_ctx["high_risk"] = True
        extra_ctx["hide_allow_always"] = True
        record_decision(tool_name, "SOCIAL_IRREVERSIBLE_GATE_ESCALATED", call.reason)

    if call.action == PermissionAction.ALLOW and is_financial_or_spend_tool(tool_name, tool_input):
        call.action = PermissionAction.ASK
        call.reason = f"Financial spend operation ({tool_name}) requires explicit human approval"
        record_decision(tool_name, "FINANCIAL_GATE_ESCALATED", call.reason)

    is_destr, destr_reason, blast_info = is_destructive_shell_tool_call(tool_name, tool_input)
    if call.action == PermissionAction.ALLOW and is_destr:
        call.action = PermissionAction.ASK
        call.reason = (
            f"Irreversible destructive operation ({destr_reason or tool_name}) requires explicit human approval"
        )
        extra_ctx = call.context()
        extra_ctx["irreversible_destructive"] = True
        extra_ctx["high_risk"] = True
        extra_ctx["hide_allow_always"] = True
        extra_ctx["blast_radius"] = blast_info
        if snapshot_id := pre_destructive_snapshot_id():
            extra_ctx["snapshot_id"] = snapshot_id
        record_decision(tool_name, "DESTRUCTIVE_IRREVERSIBLE_GATE_ESCALATED", call.reason)

    if (
        call.action == PermissionAction.ALLOW
        and ctx.auto_mode_enabled
        and not ctx.is_cron  # nobody can lift a scheduled run's suspension; the job's declaration answers each ask
        and (breach := is_threshold_breached(ctx.session_key)) != ThresholdBreach.NONE
    ):
        call.action = PermissionAction.ASK
        call.reason = f"Auto-mode suspended ({breach.value} denial threshold breached) — explicit approval required"
        extra_ctx = call.context()
        extra_ctx["auto_mode_suspended"] = breach.value
        extra_ctx["high_risk"] = True
        extra_ctx["hide_allow_always"] = True
        record_decision(tool_name, "AUTO_MODE_SUSPENDED_ALLOW_ESCALATED", call.reason)
