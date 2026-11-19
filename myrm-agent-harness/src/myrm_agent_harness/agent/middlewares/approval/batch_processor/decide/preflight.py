"""[INPUT]
- myrm_agent_harness.agent.security.audit::record_decision (POS: Security audit log — re-exported from core.security.audit.)
- myrm_agent_harness.agent.security.guards.untrusted_ingress_fence::is_tool_allowed_under_untrusted_ingress / is_untrusted_ingress_active (POS: Layer 2 runtime security guard. Sits between Inbound Task Ingress and Agent Tool Registry.)
- myrm_agent_harness.core.security.readonly_research_sandbox::get_readonly_research_sandbox_facade (POS: Entry of the read-only research lease package.)
- myrm_agent_harness.agent.middlewares.approval.denial_diagnostic_bridge::build_auto_review_denial_message (POS: Gives the model something to act on instead of a bare refusal. Used by batch_processor to word the refusals of the read-only lease, the permission engine, the shell-escalation check and the LLM security review.)
- myrm_agent_harness.agent.middlewares.approval.helpers::record_denial (POS: Approval middleware helper functions. Implements dual-threshold denial tracking (consecutive + total) with proactive guidance on every denial and automatic consecutive counter reset on any allowed operation.)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.yolo::operator_as_key_deny_message (POS: batch_processor 的 YOLO 分支；由 core 在确认 YOLO 可用、且不是定时运行时调用。)
- myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.state::BatchContext / CallState / Verdicts (POS: Shared state of the decision stages in ``decide/``: the stages read the batch context, write the call state, and settle a call by writing it into the verdict lists.)

[OUTPUT]
- deny_before_policy: refuse a call that no policy may weigh, and say whether it was refused

[POS]
First decision stage. Three gates that apply before any policy is read and that no rule, allowlist entry or YOLO
setting lifts: a lone printable operator as a vision key name, a tool denied under untrusted ingress, and a write
blocked by the read-only research lease.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.guards.untrusted_ingress_fence import (
    is_tool_allowed_under_untrusted_ingress,
    is_untrusted_ingress_active,
)
from myrm_agent_harness.core.security.readonly_research_sandbox import get_readonly_research_sandbox_facade

from ...denial_diagnostic_bridge import build_auto_review_denial_message
from ...helpers import record_denial
from ..yolo import operator_as_key_deny_message
from .state import BatchContext, CallState, Verdicts

logger = logging.getLogger(__name__)


def deny_before_policy(ctx: BatchContext, verdicts: Verdicts, call: CallState) -> bool:
    """Refuse the call when one of the pre-policy gates stops it; True when it was refused."""
    tool_name = call.tool_name

    operator_deny = operator_as_key_deny_message(tool_name, call.tool_input)
    if operator_deny is not None:
        logger.warning(
            "[OPERATOR_AS_KEY] Auto-deny %s before HITL (session: %s)",
            tool_name,
            ctx.session_key,
        )
        record_decision(
            tool_name,
            "OPERATOR_AS_KEY_DENY",
            "Lone printable operator rejected as vision key name",
        )
        verdicts.deny(call, operator_deny)
        return True

    if is_untrusted_ingress_active() and not is_tool_allowed_under_untrusted_ingress(tool_name):
        logger.warning(
            "[INGRESS_FENCE] Auto-deny %s under untrusted ingress (session: %s)",
            tool_name,
            ctx.session_key,
        )
        record_decision(
            tool_name,
            "INGRESS_FENCE_DENY",
            f"Tool '{tool_name}' stripped under untrusted ingress",
        )
        verdicts.deny(call, f"Untrusted ingress fence: tool '{tool_name}' stripped for external tasks")
        return True

    ro_allowed, ro_reason = get_readonly_research_sandbox_facade().evaluate_tool(ctx.session_key, tool_name)
    if not ro_allowed:
        logger.warning(
            "[READONLY_RESEARCH_LEASE] Tool %s DENIED (session: %s): %s",
            tool_name,
            ctx.session_key,
            ro_reason,
        )
        record_decision(tool_name, "READONLY_RESEARCH_LEASE_BLOCKED", ro_reason)
        hint = record_denial(tool_name, ctx.session_key)
        verdicts.deny(call, build_auto_review_denial_message(tool_name, ro_reason, hint))
        return True

    return False
