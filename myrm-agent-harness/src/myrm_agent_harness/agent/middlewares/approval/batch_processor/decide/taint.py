"""[INPUT]
- myrm_agent_harness.agent.security.audit::record_decision (POS: Security audit log — re-exported from core.security.audit.)
- myrm_agent_harness.agent.security.guards.taint_tracker::get_taint_tracker / TaintLabel (POS: Layer 2 enhancement. Sits between tool_interceptor (records taint after tool execution) and tool_approval (checks taint before tool execution). Prevents the classic prompt-injection → command-injection attack chain by escalating suspicious tool calls to user approval.)
- myrm_agent_harness.agent.security.types::PermissionAction / ReviewDecision (POS: Security type definitions — re-exported from core.security.types.)
- myrm_agent_harness.core.security.spend_governance::is_irreversible_social_action (POS: Foundational Agent Commerce governance module in core/security/.)
- myrm_agent_harness.agent.middlewares.approval._batch_review::_security_reviewer / _run_llm_review / _truncate_tool_args (POS: Batch review helpers — LLM review and runtime domain tracking.)
- myrm_agent_harness.agent.middlewares.approval.helpers::ThresholdBreach / is_threshold_breached / record_approval / record_denial (POS: Approval middleware helper functions. Implements dual-threshold denial tracking (consecutive + total) with proactive guidance on every denial and automatic consecutive counter reset on any allowed operation.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState / Verdicts (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- find_taint_conflict: the taint labels of the session that forbid this call, with their sources
- escalate_tainted: send a tainted ALLOW back to ASK, or let the security reviewer settle it

[POS]
Fifth decision stage, for an ALLOW only. A tool whose sink policy conflicts with what the session has ingested is not
auto-approved: it goes to a person, unless auto mode's security reviewer, shown the labels and their sources, settles it.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.types import PermissionAction, ReviewDecision
from myrm_agent_harness.core.security.spend_governance import is_irreversible_social_action

from ... import _batch_review
from ..._batch_review import _run_llm_review, _truncate_tool_args
from ...helpers import (
    ThresholdBreach,
    is_threshold_breached,
    record_approval,
    record_denial,
)
from .state import BatchContext, CallState, Verdicts

if TYPE_CHECKING:
    from myrm_agent_harness.agent.security.guards.taint_tracker import TaintLabel

logger = logging.getLogger(__name__)

_MAX_SOURCES_SHOWN = 5


def find_taint_conflict(ctx: BatchContext, call: CallState) -> dict[TaintLabel, set[str]] | None:
    """The session's taint labels that conflict with this tool's sink policy; None when there is no conflict."""
    from myrm_agent_harness.agent.security.guards.taint_tracker import (
        get_taint_tracker,
    )

    trusted_net = getattr(ctx.config, "network_allowlist", None)
    return get_taint_tracker().check_sink(
        call.tool_name,
        tool_input=call.tool_input,
        trusted_hosts=trusted_net,
    )


async def escalate_tainted(
    ctx: BatchContext,
    verdicts: Verdicts,
    call: CallState,
    taint_conflict: dict[TaintLabel, set[str]],
) -> bool:
    """Escalate the ALLOW to ASK; True when the security reviewer settled the call instead."""
    tool_name, tool_input = call.tool_name, call.tool_input

    # taint_conflict is a dict mapping TaintLabel to a set of sources
    conflict_labels = list(taint_conflict.keys())
    conflict_str = ", ".join(conflict_labels)

    # Format labels with sources for the LLM reviewer
    formatted_labels: set[str] = set()
    for label, sources in taint_conflict.items():
        if sources:
            # Defensive truncation to prevent prompt explosion from too many sources
            sources_list = list(sources)
            if len(sources_list) > _MAX_SOURCES_SHOWN:
                truncated_sources = sources_list[:_MAX_SOURCES_SHOWN]
                sources_str = (
                    ", ".join(truncated_sources) + f" ... and {len(sources_list) - _MAX_SOURCES_SHOWN} more sources"
                )
            else:
                sources_str = ", ".join(sources_list)
            formatted_labels.add(f"{label} (Sources: {sources_str})")
        else:
            formatted_labels.add(label)

    logger.warning(
        "[TAINT] Escalating %s from ALLOW to ASK: session contains %s data",
        tool_name,
        conflict_str,
    )
    record_decision(
        tool_name,
        "TAINT_ESCALATE",
        f"session contains {conflict_str} data",
        tainted=True,
    )
    call.action = PermissionAction.ASK
    call.reason = f"Taint policy: session contains {conflict_str} data"
    call.context()["high_risk"] = True

    # Smart Intent Guard: Try LLM review for taint conflict if enabled
    if not (
        ctx.auto_mode_enabled
        and _batch_review._security_reviewer is not None
        and is_threshold_breached(ctx.session_key) == ThresholdBreach.NONE
        and not is_irreversible_social_action(tool_name, tool_input)
    ):
        return False

    safe_tool_input = _truncate_tool_args(tool_input)
    command_repr = f"Tool: {tool_name}\nArgs: {json.dumps(safe_tool_input)}"
    review_result = await _run_llm_review(
        command_repr,
        ctx.workspace_root,
        intent_context=ctx.intent_context,
        taint_labels=frozenset(formatted_labels),
        recent_tool_calls=ctx.recent_tool_calls,
        model_id=ctx.config.auto_review_model,
        trusted_domains=ctx.config.network_allowlist,
    )
    if review_result is None:
        return False

    if review_result.decision == ReviewDecision.ALLOW:
        logger.info(
            "[LLM_REVIEW] Auto-allowed tainted %s: %s",
            tool_name,
            review_result.reason,
        )
        record_decision(tool_name, "LLM_REVIEW_ALLOW", review_result.reason)
        verdicts.approve(call)
        record_approval(ctx.session_key)
        return True
    if review_result.decision == ReviewDecision.DENY:
        logger.warning(
            "[LLM_REVIEW] Denied tainted %s: %s",
            tool_name,
            review_result.reason,
        )
        record_decision(tool_name, "LLM_REVIEW_DENY", review_result.reason)
        hint = record_denial(tool_name, ctx.session_key)
        verdicts.deny(call, f"Denied by security review (Taint): {review_result.reason}{hint}")
        return True
    if review_result.decision == ReviewDecision.UNCERTAIN:
        logger.info(
            "[LLM_REVIEW] Uncertain about tainted %s: %s",
            tool_name,
            review_result.reason,
        )
        call.reason = f"{call.reason}\n\n AI Security Reviewer Note:\n{review_result.reason}"
        call.context()["high_risk"] = True
    return False
