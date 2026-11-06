"""YOLO 模式的批量自动批准/拒绝。

[POS]
batch_processor 的 YOLO 分支；由 core 在确认 YOLO 可用后调用。
"""



from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.engine import (
    evaluate_tool_call,
)
from myrm_agent_harness.agent.security.guards.untrusted_ingress_fence import (
    is_tool_allowed_under_untrusted_ingress,
    is_untrusted_ingress_active,
)
from myrm_agent_harness.agent.security.tool_registry import (
    resolve_permission_type,
)
from myrm_agent_harness.agent.security.types import (
    PermissionAction,
    SecurityConfig,
)
from myrm_agent_harness.core.security.readonly_research_sandbox import get_readonly_research_sandbox_facade
from myrm_agent_harness.core.security.spend_governance import (
    compute_action_digest,
    is_financial_or_spend_tool,
    is_irreversible_social_action,
    parse_spend_amount,
)
from myrm_agent_harness.toolkits.code_execution.security.ast_parser import (
    is_destructive_shell_tool_call,
)

from ..denial_diagnostic_bridge import build_auto_review_denial_message

_VISION_KEY_TOOL_NAMES = frozenset({"desktop_vision_tool", "desktop_vision"})

def operator_as_key_deny_message(tool_name: str, tool_input: dict[str, object]) -> str | None:
    """Fail-closed before HITL: lone printable operators are never key names.

    Matches ``desktop_vision_action`` runtime Safety + REMEDY_HINT so the model
    receives the same remediation without an approval card or display I/O.
    """
    if tool_name not in _VISION_KEY_TOOL_NAMES:
        return None
    if str(tool_input.get("action", "") or "").strip().lower() != "key":
        return None
    text = tool_input.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    from myrm_agent_harness.toolkits.computer_use import safety

    blocked = safety.is_operator_as_key_name(text)
    if blocked is None:
        return None
    remedy = (
        "[REMEDY_HINT: Printable operators are not keyboard key names. "
        "Use action=type to enter the character, or desktop_interact_tool "
        "to click the calculator/@dref button.]"
    )
    return f"Safety: {blocked}\n{remedy}"


logger = logging.getLogger(__name__)


async def _evaluate_yolo_batch(
    tool_calls: list[ToolCall],
    config: SecurityConfig,
    *,
    workspace_root: str | None,
    session_key: str,
) -> tuple[
    list[tuple[int, ToolCall]],
    list[tuple[int, ToolCall, str]],
    list[tuple[int, ToolCall, str, str, dict[str, Any] | None]],
]:
    auto_approved: list[tuple[int, ToolCall]] = []
    auto_denied: list[tuple[int, ToolCall, str]] = []
    pending_approval: list[tuple[int, ToolCall, str, str, dict[str, Any] | None]] = []

    suffix = "" if not config.yolo_mode_timeout else f" (expires in {config.yolo_mode_timeout}s)"
    logger.info(
        "[YOLO] Auto-approving tool calls%s (session: %s)",
        suffix,
        session_key,
    )
    for idx, tool_call in enumerate(tool_calls):
        tool_name = tool_call.get("name", "unknown")
        tool_input: dict[str, object] = tool_call.get("args", {})
        operator_deny = operator_as_key_deny_message(tool_name, tool_input)
        if operator_deny is not None:
            logger.warning(
                "[OPERATOR_AS_KEY] Auto-deny %s before YOLO/HITL (session: %s)",
                tool_name,
                session_key,
            )
            record_decision(
                tool_name,
                "OPERATOR_AS_KEY_DENY",
                "Lone printable operator rejected as vision key name",
            )
            auto_denied.append((idx, tool_call, operator_deny))
            continue
        if is_untrusted_ingress_active() and not is_tool_allowed_under_untrusted_ingress(tool_name):
            logger.warning(
                "[INGRESS_FENCE] Tool %s DENIED under untrusted ingress (YOLO overridden)",
                tool_name,
            )
            record_decision(
                tool_name,
                "INGRESS_FENCE_YOLO_BLOCKED",
                f"Tool '{tool_name}' stripped under untrusted ingress",
            )
            auto_denied.append(
                (
                    idx,
                    tool_call,
                    f"Untrusted ingress fence: tool '{tool_name}' stripped for external tasks",
                )
            )
            continue

        ro_allowed, ro_reason = get_readonly_research_sandbox_facade().evaluate_tool(session_key, tool_name)
        if not ro_allowed:
            logger.warning(
                "[READONLY_RESEARCH_LEASE] Tool %s DENIED under YOLO (session: %s): %s",
                tool_name,
                session_key,
                ro_reason,
            )
            record_decision(tool_name, "READONLY_RESEARCH_LEASE_BLOCKED", ro_reason)
            auto_denied.append((idx, tool_call, build_auto_review_denial_message(tool_name, ro_reason)))
            continue

        permission_type = resolve_permission_type(tool_name, tool_input)
        action, reason = evaluate_tool_call(
            permission_type,
            tool_input,
            config,
            workspace_root=workspace_root,
            tool_name=tool_name,
        )
        if action == PermissionAction.DENY:
            logger.warning(
                "[YOLO] Tool %s DENIED despite YOLO mode: %s (session: %s)",
                tool_name,
                reason,
                session_key,
            )
            record_decision(tool_name, "YOLO_DENY_OVERRIDE", reason)
            auto_denied.append((idx, tool_call, build_auto_review_denial_message(tool_name, reason)))
        elif is_financial_or_spend_tool(tool_name, tool_input):
            logger.warning(
                "[YOLO_FINANCIAL_GATE] Tool %s blocked from YOLO auto-approval (financial spend detected)",
                tool_name,
            )
            record_decision(
                tool_name,
                "YOLO_FINANCIAL_GATE_BLOCKED",
                "Financial spend tools are immune to YOLO auto-approval",
            )
            spend_amt, spend_cur = parse_spend_amount(tool_input)
            spend_digest = compute_action_digest(tool_name, tool_input)
            spend_ctx: dict[str, object] = {
                "is_spend": True,
                "spend_amount": spend_amt,
                "spend_currency": spend_cur,
                "action_digest": spend_digest,
                "high_risk": True,
                "hide_allow_always": True,
            }
            disp_amt = f"{spend_amt:.2f} {spend_cur}" if spend_amt is not None else "transaction"
            pending_approval.append(
                (
                    idx,
                    tool_call,
                    permission_type,
                    f"Financial spend operation requires explicit approval ({disp_amt})",
                    spend_ctx,
                )
            )
        elif is_irreversible_social_action(tool_name, tool_input):
            logger.warning(
                "[YOLO_SOCIAL_IRREVERSIBLE_GATE] Tool %s blocked from YOLO auto-approval (socially irreversible)",
                tool_name,
            )
            record_decision(
                tool_name,
                "YOLO_SOCIAL_IRREVERSIBLE_BLOCKED",
                "Socially irreversible operations are immune to YOLO auto-approval",
            )
            irreversible_ctx: dict[str, object] = {
                "socially_irreversible": True,
                "high_risk": True,
                "hide_allow_always": True,
            }
            pending_approval.append(
                (
                    idx,
                    tool_call,
                    permission_type,
                    f"Socially irreversible operation ({tool_name}) requires explicit human approval",
                    irreversible_ctx,
                )
            )
        else:
            is_destr, destr_reason, blast_info = is_destructive_shell_tool_call(tool_name, tool_input)
            if is_destr:
                logger.warning(
                    "[YOLO_DESTRUCTIVE_IRREVERSIBLE_GATE] Tool %s blocked from YOLO auto-approval (%s)",
                    tool_name,
                    destr_reason,
                )
                record_decision(
                    tool_name,
                    "YOLO_DESTRUCTIVE_IRREVERSIBLE_BLOCKED",
                    f"Irreversible destructive operations are immune to YOLO auto-approval: {destr_reason}",
                )
                from pathlib import Path

                from myrm_agent_harness.toolkits.code_execution.security.workspace_snapshot import (
                    create_workspace_snapshot,
                )

                snap_res = create_workspace_snapshot(Path.cwd())
                destr_ctx: dict[str, object] = {
                    "irreversible_destructive": True,
                    "high_risk": True,
                    "hide_allow_always": True,
                    "blast_radius": blast_info,
                    "snapshot_id": snap_res.snapshot_id,
                }
                pending_approval.append(
                    (
                        idx,
                        tool_call,
                        permission_type,
                        f"Irreversible destructive operation ({destr_reason or tool_name}) requires explicit human approval",
                        destr_ctx,
                    )
                )
            else:
                record_decision(tool_name, "YOLO_AUTO_APPROVE", "YOLO mode enabled")
                auto_approved.append((idx, tool_call))
    return auto_approved, auto_denied, pending_approval
