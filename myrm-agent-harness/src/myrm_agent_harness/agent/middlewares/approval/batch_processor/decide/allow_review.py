"""[INPUT]
- myrm_agent_harness.agent.security.audit::record_decision (POS: Security audit log — re-exported from core.security.audit.)
- myrm_agent_harness.agent.security.types::ReviewDecision (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.toolkits.code_execution.security.risk_classifier::CommandRiskLevel / classify_command_risk (POS: Command risk classifier for approval auto-allow decisions.)
- myrm_agent_harness.agent.middlewares.approval._batch_review::_security_reviewer / _run_llm_review / _truncate_tool_args (POS: Batch review helpers — LLM review and runtime domain tracking.)
- myrm_agent_harness.agent.middlewares.approval.denial_diagnostic_bridge::build_auto_review_denial_message (POS: Gives the model something to act on instead of a bare refusal. Used by batch_processor to word the refusals of the read-only lease, the permission engine, the shell-escalation check and the LLM security review.)
- myrm_agent_harness.agent.middlewares.approval.helpers::ThresholdBreach / is_threshold_breached / record_approval / record_denial (POS: Approval middleware helper functions. Implements dual-threshold denial tracking (consecutive + total) with proactive guidance on every denial and automatic consecutive counter reset on any allowed operation.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState / Verdicts (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- settle_allowed: approve an ALLOW, after auto mode's outbound and shell reviews, or hand it back to a person or a refusal

[POS]
Fifth decision stage, for an ALLOW the taint check left alone. In auto mode a delegation to an external agent and a
shell command that is not trivially safe still go through the security reviewer, so a broad user ALLOW rule or a
prompt-injected delegation cannot skip the review; everything else is approved here.
"""

from __future__ import annotations

import json
import logging

from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.types import ReviewDecision

from ... import _batch_review
from ..._batch_review import _run_llm_review, _truncate_tool_args
from ...denial_diagnostic_bridge import build_auto_review_denial_message
from ...helpers import (
    ThresholdBreach,
    is_threshold_breached,
    record_approval,
    record_denial,
)
from .state import BatchContext, CallState, Verdicts

logger = logging.getLogger(__name__)


async def settle_allowed(ctx: BatchContext, verdicts: Verdicts, call: CallState) -> None:
    """Settle an ALLOW that carries no taint conflict: approved, refused or parked for a person."""
    if await _settled_by_outbound_review(ctx, verdicts, call):
        return
    if await _settled_by_shell_review(ctx, verdicts, call):
        return

    record_decision(call.tool_name, "ALLOW", call.reason)
    verdicts.approve(call)
    record_approval(ctx.session_key)


def _auto_review_available(ctx: BatchContext) -> bool:
    """Auto mode is on, a reviewer is registered, and no denial threshold suspends auto mode."""
    return (
        ctx.auto_mode_enabled
        and _batch_review._security_reviewer is not None
        and is_threshold_breached(ctx.session_key) == ThresholdBreach.NONE
    )


async def _settled_by_outbound_review(ctx: BatchContext, verdicts: Verdicts, call: CallState) -> bool:
    """Review a delegation to an external agent; True when the reviewer refused it or parked it for a person.

    An external CLI action that passes the engine as ALLOW is still reviewed in auto mode, so a prompt-injected
    delegation cannot ride a broad ALLOW rule.
    """
    if call.permission_type != "invoke_external_agent" or not _auto_review_available(ctx):
        return False

    tool_name = call.tool_name
    safe_tool_input = _truncate_tool_args(call.tool_input)
    command_repr = f"Tool: {tool_name}\nArgs: {json.dumps(safe_tool_input, ensure_ascii=False, default=str)}"
    review_result = await _run_llm_review(
        command_repr,
        ctx.workspace_root,
        intent_context=ctx.intent_context,
        recent_tool_calls=ctx.recent_tool_calls,
        model_id=ctx.config.auto_review_model,
        trusted_domains=ctx.config.network_allowlist,
    )
    if review_result is None:
        return False

    if review_result.decision == ReviewDecision.DENY:
        logger.warning(
            "[OUTBOUND_CHECK] Denied delegation %s: %s",
            tool_name,
            review_result.reason,
        )
        record_decision(tool_name, "OUTBOUND_DENY", review_result.reason)
        hint = record_denial(tool_name, ctx.session_key)
        verdicts.deny(call, f"Delegation denied by outbound security check: {review_result.reason}{hint}")
        return True
    if review_result.decision == ReviewDecision.UNCERTAIN:
        logger.info(
            "[OUTBOUND_CHECK] Uncertain about delegation %s: %s",
            tool_name,
            review_result.reason,
        )
        record_decision(tool_name, "OUTBOUND_UNCERTAIN", review_result.reason)
        call.context()["high_risk"] = True
        verdicts.hold(call, f"Delegation needs review: {review_result.reason}")
        return True
    record_decision(
        tool_name,
        "OUTBOUND_ALLOW",
        "delegation cleared by outbound check",
    )
    return False


async def _settled_by_shell_review(ctx: BatchContext, verdicts: Verdicts, call: CallState) -> bool:
    """Review a shell command that is not trivially safe; True when the reviewer refused it or parked it for a person.

    A shell call that passes the engine as ALLOW is still reviewed in auto mode when the risk classifier does not
    call the command safe, so a broad user ALLOW rule cannot bypass the reviewer.
    """
    if call.permission_type not in ("shell_exec", "code_interpreter") or not _auto_review_available(ctx):
        return False

    from myrm_agent_harness.toolkits.code_execution.security.risk_classifier import (
        CommandRiskLevel,
        classify_command_risk,
    )

    tool_name, tool_input = call.tool_name, call.tool_input
    shell_cmd = str(tool_input.get("command", "") or tool_input.get("code", "") or tool_input.get("data", "")).strip()
    if not shell_cmd or not (
        getattr(ctx.config, "classify_all_shell_in_auto_mode", False)
        or classify_command_risk(shell_cmd) != CommandRiskLevel.SAFE
    ):
        return False

    if call.extra_ctx and "ptc_annotations" in call.extra_ctx:
        shell_cmd = f"{shell_cmd}\n\n# PTC Annotations: {call.extra_ctx['ptc_annotations']}"
    review_result = await _run_llm_review(
        shell_cmd,
        ctx.workspace_root,
        intent_context=ctx.intent_context,
        recent_tool_calls=ctx.recent_tool_calls,
        model_id=ctx.config.auto_review_model,
        trusted_domains=ctx.config.network_allowlist,
    )
    if review_result is None:
        return False

    if review_result.decision == ReviewDecision.DENY:
        logger.warning(
            "[SHELL_ESCALATION] Denied %s (ALLOW→DENY): %s",
            tool_name,
            review_result.reason,
        )
        record_decision(
            tool_name,
            "SHELL_ESCALATION_DENY",
            review_result.reason,
        )
        hint = record_denial(tool_name, ctx.session_key)
        if ctx.is_interactive:
            extra_ctx = call.context()
            extra_ctx["smart_denied"] = True
            extra_ctx["reviewer_reason"] = review_result.reason
            call.reason = f"AI Security Reviewer recommends denial: {review_result.reason}"
            verdicts.hold(call, call.reason)
        else:
            denial_reason = f"Denied by auto-mode shell escalation: {review_result.reason}"
            verdicts.deny(call, build_auto_review_denial_message(tool_name, denial_reason, hint))
        return True
    if review_result.decision == ReviewDecision.UNCERTAIN:
        logger.info(
            "[SHELL_ESCALATION] Uncertain about %s: %s",
            tool_name,
            review_result.reason,
        )
        record_decision(
            tool_name,
            "SHELL_ESCALATION_UNCERTAIN",
            review_result.reason,
        )
        call.context()["high_risk"] = True
        verdicts.hold(call, f"Shell command needs review: {review_result.reason}")
        return True
    record_decision(
        tool_name,
        "SHELL_ESCALATION_ALLOW",
        "shell command cleared by escalation check",
    )
    return False
