"""[INPUT]
- myrm_agent_harness.agent.security.approval_reason::is_human_only (POS: The seam between the engine, which writes a reason once in English, and the cards (web, channel), which word the same decision in the viewer's language. The code is read by whoever renders the card; the text is never parsed. The same code tells the automatic approvers (YOLO mode, the AI security reviewer, an approval expiry) which asks are not theirs to answer.)
- myrm_agent_harness.agent.security.audit::record_decision (POS: Security audit log — re-exported from core.security.audit.)
- myrm_agent_harness.agent.security.command_rules::COMMAND_BEARING_PERMISSIONS / command_text (POS: Pure helpers of ``engine.py``, of the command-egress check in ``guards/taint_tracker.py`` and of the approval stages that read a command: the engine owns the order of the layers, this module owns which tool inputs carry a command, which field of them the tool runs and what a command line means to a rule, so every judge sees the command the shell will run and no other text.)
- myrm_agent_harness.agent.security.engine::extract_url_domains (POS: Layers 1–5 of the security architecture. Pure deterministic evaluation — no side effects, no I/O, trivially testable.)
- myrm_agent_harness.agent.security.types::ReviewDecision (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.core.security.spend_governance::is_financial_or_spend_tool / is_irreversible_social_action (POS: Foundational Agent Commerce governance module in core/security/.)
- myrm_agent_harness.agent.middlewares.approval._batch_review::_security_reviewer / _get_runtime_domains / _run_llm_review / _truncate_tool_args (POS: Batch review helpers — LLM review and runtime domain tracking.)
- myrm_agent_harness.agent.middlewares.approval._cron_settle::settle_ask (POS: A run with no approver (a scheduled job, and every agent it delegates to) cannot be paused for an answer: nothing resumes it, so the job would end half done. The job's declared capabilities answer instead, whether the ask comes from the job's own agent, a delegated agent, a workflow node, or a branch that lets no ask through on its own. A call the allowlist or the reviewer approved is checked again against the classes no approval covers.)
- myrm_agent_harness.agent.middlewares.approval.denial_diagnostic_bridge::build_auto_review_denial_message (POS: Gives the model something to act on instead of a bare refusal. Used by batch_processor to word the refusals of the read-only lease, the permission engine, the shell-escalation check and the LLM security review.)
- myrm_agent_harness.agent.middlewares.approval.helpers::ThresholdBreach / is_threshold_breached / record_approval / record_denial (POS: Approval middleware helper functions. Implements dual-threshold denial tracking (consecutive + total) with proactive guidance on every denial and automatic consecutive counter reset on any allowed operation.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState / Verdicts (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- settle_denied: refuse a DENY verdict with the wording the model reads
- settle_cron_ask: answer an ASK of a run with no approver from the job's declaration
- settle_runtime_domain: approve a browser call whose domains a person already approved in this session
- review_before_asking: let auto mode's security reviewer settle an ASK (never a payment, a socially irreversible call or a write only a person may answer), or mark it high risk when auto mode is suspended

[POS]
Last settling stages of the decision loop, for a call that is not approved: a DENY is refused, an ASK of a scheduled
run is answered by its job, and an ASK of an attended run may still be approved by a session domain grant or by the
security reviewer before a person is asked.
"""

from __future__ import annotations

import json
import logging

from myrm_agent_harness.agent.security.approval_reason import is_human_only
from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.command_rules import COMMAND_BEARING_PERMISSIONS, command_text
from myrm_agent_harness.agent.security.engine import extract_url_domains
from myrm_agent_harness.agent.security.types import ReviewDecision
from myrm_agent_harness.core.security.spend_governance import (
    is_financial_or_spend_tool,
    is_irreversible_social_action,
)

from ... import _batch_review
from ..._batch_review import (
    _get_runtime_domains,
    _run_llm_review,
    _truncate_tool_args,
)
from ..._cron_settle import settle_ask
from ...denial_diagnostic_bridge import build_auto_review_denial_message
from ...helpers import (
    ThresholdBreach,
    is_threshold_breached,
    record_approval,
    record_denial,
)
from .state import BatchContext, CallState, Verdicts

logger = logging.getLogger(__name__)


def settle_denied(ctx: BatchContext, verdicts: Verdicts, call: CallState) -> None:
    """Refuse a call the policy denied."""
    logger.warning("[SECURITY] Tool %s DENIED: %s", call.tool_name, call.reason)
    record_decision(call.tool_name, "DENY", call.reason)
    hint = record_denial(call.tool_name, ctx.session_key)
    verdicts.deny(call, build_auto_review_denial_message(call.tool_name, call.reason, hint))


def settle_cron_ask(ctx: BatchContext, verdicts: Verdicts, call: CallState) -> None:
    """Answer an ASK of a run with no approver: the job's declared capabilities approve it or refuse it."""
    refusal = settle_ask(
        permission_type=call.permission_type,
        tool_name=call.tool_name,
        tool_input=call.tool_input,
        config=ctx.config,
        workspace_root=ctx.workspace_root,
        session_key=ctx.session_key,
    )
    if refusal is None:
        verdicts.approve(call)
    else:
        verdicts.deny(call, refusal)


def settle_runtime_domain(ctx: BatchContext, verdicts: Verdicts, call: CallState) -> bool:
    """Approve a navigation whose every domain was approved earlier in the session; True when it was approved."""
    if not ctx.config.domain_hitl_enabled:
        return False
    domains = extract_url_domains(call.permission_type, call.tool_input)
    if not domains:
        return False
    runtime_domains = _get_runtime_domains()
    if not all(d in runtime_domains for d in domains):
        return False

    logger.warning(
        "[DOMAIN_HITL] Auto-allowed %s (runtime domain match: %s)",
        call.tool_name,
        domains,
    )
    record_decision(
        call.tool_name,
        "DOMAIN_RUNTIME_ALLOW",
        f"runtime domain match: {domains}",
    )
    verdicts.approve(call)
    record_approval(ctx.session_key)
    return True


async def review_before_asking(ctx: BatchContext, verdicts: Verdicts, call: CallState) -> bool:
    """Let auto mode's security reviewer judge an ASK; True when it approved the call or refused it.

    An uncertain verdict leaves the ASK in place and marks it high risk. A payment, a socially irreversible call and a
    write only a person may answer are never put to the reviewer: it reads what the model says about the call, and
    for these a person alone answers. While a denial threshold is breached, auto mode is suspended: the ASK is not
    reviewed and goes to a person marked high risk.
    """
    tool_name, tool_input = call.tool_name, call.tool_input
    if (
        ctx.auto_mode_enabled
        and _batch_review._security_reviewer is not None
        and is_threshold_breached(ctx.session_key) == ThresholdBreach.NONE
        and not is_irreversible_social_action(tool_name, tool_input)
        and not is_financial_or_spend_tool(tool_name, tool_input)
        and not is_human_only(call.reason)
    ):
        # Build command representation for the classifier
        if call.permission_type in COMMAND_BEARING_PERMISSIONS:
            command = command_text(call.permission_type, tool_input)
            if call.extra_ctx and "ptc_annotations" in call.extra_ctx:
                command = f"{command}\n\n# PTC Annotations: {call.extra_ctx['ptc_annotations']}"
        else:
            safe_args = _truncate_tool_args(tool_input)
            command = f"Tool: {tool_name}\nArgs: {json.dumps(safe_args, ensure_ascii=False, default=str)}"

        if command:
            review_result = await _run_llm_review(
                command,
                ctx.workspace_root,
                intent_context=ctx.intent_context,
                taint_labels=ctx.taint_labels,
                recent_tool_calls=ctx.recent_tool_calls,
                model_id=ctx.config.auto_review_model,
                trusted_domains=ctx.config.network_allowlist,
            )
            if review_result is not None:
                if review_result.decision == ReviewDecision.ALLOW:
                    logger.info(
                        "[LLM_REVIEW] Auto-allowed %s: %s",
                        tool_name,
                        review_result.reason,
                    )
                    record_decision(tool_name, "LLM_REVIEW_ALLOW", review_result.reason)
                    verdicts.approve(call)
                    record_approval(ctx.session_key)
                    return True
                if review_result.decision == ReviewDecision.DENY:
                    logger.warning(
                        "[LLM_REVIEW] Denied %s: %s",
                        tool_name,
                        review_result.reason,
                    )
                    record_decision(tool_name, "LLM_REVIEW_DENY", review_result.reason)
                    if ctx.is_interactive:
                        extra_ctx = call.context()
                        extra_ctx["smart_denied"] = True
                        extra_ctx["reviewer_reason"] = review_result.reason
                        call.reason = f"AI Security Reviewer recommends denial: {review_result.reason}"
                        verdicts.hold(call, call.reason)
                    else:
                        hint = record_denial(tool_name, ctx.session_key)
                        denial_reason = f"Denied by security review: {review_result.reason}"
                        verdicts.deny(call, build_auto_review_denial_message(tool_name, denial_reason, hint))
                    return True
                record_decision(tool_name, "LLM_REVIEW_UNCERTAIN", review_result.reason)
                call.reason = f"{call.reason}\n\nAI Security Reviewer: {review_result.reason}"
                call.context()["high_risk"] = True

    elif ctx.auto_mode_enabled and is_threshold_breached(ctx.session_key) != ThresholdBreach.NONE:
        breach = is_threshold_breached(ctx.session_key)
        logger.warning(
            "[AUTO_MODE_SUSPENDED] Denial threshold breached (%s) — "
            "tool %s falling through to HITL approval (session: %s)",
            breach.value,
            tool_name,
            ctx.session_key,
        )
        record_decision(tool_name, "AUTO_MODE_SUSPENDED", f"denial threshold: {breach.value}")
        extra_ctx = call.context()
        extra_ctx["high_risk"] = True
        extra_ctx["auto_mode_suspended"] = breach.value
    return False
