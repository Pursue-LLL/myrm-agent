"""The approval interrupt payload the client renders its card from.

[INPUT]
- agent.security.approval_reason::CodedReason (POS: an engine reason that remembers its stable code, for the card to word)
- agent.security.engine::extract_url_domains (POS: the domains a call reaches, for per-domain approval)
- agent.security.session_access::plan_directory_grants (POS: the folders a path approval can also grant)
- core.security.redact::redact_for_display (POS: arguments shown to the human are redacted)
- toolkits.code_execution.security.command_explainer.extract::build_shell_approval_fields (POS: shell command spans and risks)

[OUTPUT]
- build_interrupt_payload: Build LangChain-standard interrupt payload for batch approval (includes optional command_spans for shell tools).

[POS]
The outbound half of batch approval; the user's answer comes back through `_batch_decisions.apply_approval_decisions`.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.approval_reason import CodedReason
from myrm_agent_harness.agent.security.engine import extract_url_domains
from myrm_agent_harness.agent.security.session_access import (
    PATH_WRITE_PERMISSION_TYPES,
    merge_path_policy_with_session_access,
    plan_directory_grants,
)
from myrm_agent_harness.agent.security.types import PathPolicy
from myrm_agent_harness.core.security.redact import redact_for_display

logger = logging.getLogger(__name__)

_DEFAULT_APPROVAL_TIMEOUT_SECONDS = 600
_DEFAULT_TIMEOUT_BEHAVIOR = "deny"


def build_interrupt_payload(
    pending_approval: list[tuple[int, ToolCall, str, str, dict[str, Any] | None]],
    session_key: str,
    *,
    approval_timeout_seconds: int | None = None,
    timeout_behavior: str = _DEFAULT_TIMEOUT_BEHAVIOR,
    workspace_root: str | None = None,
    path_policy: PathPolicy | None = None,
) -> tuple[dict[str, Any], list[int]]:
    """Build LangChain-standard interrupt payload for batch approval.

    Args:
        pending_approval: list of (idx, tool_call, permission_type, reason, extra_ctx); a reason the engine
            wrote as it stands (a ``CodedReason``) also reaches the card as ``reasonCode`` and ``reasonSubject``,
            so the card words it in the viewer's language instead of showing the English text
        session_key: session identifier for routing
        approval_timeout_seconds: seconds before auto-resolution (from SecurityConfig)
        timeout_behavior: "deny" or "allow" — action taken when timeout expires
        workspace_root: the run's workspace, which relative paths resolve against
        path_policy: the configured path policy; with it, a file call naming directories outside the allowed
            zones carries ``grantDirectories`` — the folders "also grant folder access" would add

    Returns: (interrupt_payload, interrupt_indices)
    """
    action_requests = []
    review_configs = []
    interrupt_indices = []
    effective_policy = merge_path_policy_with_session_access(path_policy) if path_policy is not None else None

    for idx, tool_call, permission_type, reason, extra_ctx in pending_approval:
        tool_name = tool_call.get("name", "unknown")
        tool_input = tool_call.get("args", {})

        action_name = tool_name
        if extra_ctx and "ptc_tool_name_full" in extra_ctx:
            action_name = extra_ctx["ptc_tool_name_full"]

        redacted_args = redact_for_display(tool_input)
        action_request: dict[str, object] = {
            "action": action_name,
            "args": redacted_args,
            "description": str(reason),
        }
        if isinstance(reason, CodedReason):
            action_request["reasonCode"] = reason.code.value
            if reason.subject:
                action_request["reasonSubject"] = reason.subject
        if extra_ctx and "ptc_annotations" in extra_ctx:
            action_request["ptc_annotations"] = extra_ctx["ptc_annotations"]

        domains = extract_url_domains(permission_type, tool_input)
        if domains:
            action_request["domains"] = domains

        if effective_policy is not None:
            grants = plan_directory_grants(
                tool_input,
                policy=effective_policy,
                workspace_root=workspace_root,
                writable=permission_type in PATH_WRITE_PERMISSION_TYPES,
            )
            if grants:
                action_request["grantDirectories"] = [{"path": root.path, "writable": root.writable} for root in grants]

        from myrm_agent_harness.toolkits.code_execution.security.command_explainer.extract import (
            build_shell_approval_fields,
        )

        action_request.update(build_shell_approval_fields(tool_name, redacted_args))

        is_smart_denied = bool(extra_ctx and extra_ctx.get("smart_denied"))
        is_high_risk = bool(extra_ctx and extra_ctx.get("high_risk"))
        from myrm_agent_harness.agent.middlewares._session_context import (
            get_managed_approval_policy,
        )
        from myrm_agent_harness.agent.security.managed_policy_gates import (
            allow_always_writes_blocked,
        )

        map_blocks_allow_always = allow_always_writes_blocked(get_managed_approval_policy())
        if is_smart_denied:
            review_config: dict[str, object] = {
                "allowedDecisions": ["approve", "reject"],
                "smartDenied": True,
                "hideAllowAlways": True,
            }
            reviewer_reason = extra_ctx.get("reviewer_reason", "") if extra_ctx else ""
            if reviewer_reason:
                action_request["reviewerReason"] = reviewer_reason
        else:
            review_config = {
                "allowedDecisions": ["approve", "reject", "edit"],
            }
            if is_high_risk or map_blocks_allow_always:
                review_config["hideAllowAlways"] = True
        if extra_ctx and extra_ctx.get("hide_allow_always"):
            review_config["hideAllowAlways"] = True
        if extra_ctx and extra_ctx.get("requires_dual_insurance"):
            review_config["requiresDualInsurance"] = True
        if extra_ctx and extra_ctx.get("batch_impact_summary"):
            review_config["batchImpactSummary"] = extra_ctx.get("batch_impact_summary")
        if extra_ctx and extra_ctx.get("recovery_hint"):
            review_config["recoveryHint"] = extra_ctx.get("recovery_hint")
        if extra_ctx and extra_ctx.get("is_spend"):
            review_config["isSpend"] = True
            review_config["spendAmount"] = extra_ctx.get("spend_amount")
            review_config["spendCurrency"] = extra_ctx.get("spend_currency")
            review_config["actionDigest"] = extra_ctx.get("action_digest")
            review_config["hideAllowAlways"] = True
        if extra_ctx and extra_ctx.get("auto_mode_suspended"):
            review_config["autoModeSuspended"] = extra_ctx.get("auto_mode_suspended")
            action_request["autoModeSuspended"] = extra_ctx.get("auto_mode_suspended")
        if extra_ctx and extra_ctx.get("socially_irreversible"):
            review_config["sociallyIrreversible"] = True
            review_config["hideAllowAlways"] = True
            action_request["sociallyIrreversible"] = True
        if extra_ctx and extra_ctx.get("irreversible_destructive"):
            review_config["irreversibleDestructive"] = True
            review_config["hideAllowAlways"] = True
            review_config["blastRadius"] = extra_ctx.get("blast_radius")
            review_config["snapshotId"] = extra_ctx.get("snapshot_id")
            action_request["irreversibleDestructive"] = True
            if extra_ctx.get("snapshot_id"):
                action_request["snapshotId"] = extra_ctx.get("snapshot_id")
        if extra_ctx and extra_ctx.get("script_operand_path"):
            action_request["scriptOperandPath"] = extra_ctx.get("script_operand_path")
            action_request["scriptOperandHash"] = extra_ctx.get("script_operand_hash")
            review_config["scriptOperandProtected"] = True
        if extra_ctx and extra_ctx.get("script_content_hash"):
            review_config["scriptTarget"] = extra_ctx.get("script_target")
            review_config["scriptContentHash"] = extra_ctx.get("script_content_hash")
            action_request["scriptTarget"] = extra_ctx.get("script_target")
            action_request["scriptContentHash"] = extra_ctx.get("script_content_hash")
            review_config["scriptOperandProtected"] = True
        if domains:
            review_config["domainApproval"] = True

        action_requests.append(action_request)
        review_configs.append(review_config)
        interrupt_indices.append(idx)

    logger.info(
        "[BATCH_APPROVAL] Triggering interrupt for %d tools: %s",
        len(action_requests),
        [req["action"] for req in action_requests],
    )

    has_handover = any(perm_type == "browser_human_handover" for _, _, perm_type, _, _ in pending_approval)
    display_mode = "handover" if has_handover else "approval"

    effective_timeout = approval_timeout_seconds or _DEFAULT_APPROVAL_TIMEOUT_SECONDS
    expires_at = time.time() + effective_timeout
    request_id = str(uuid.uuid4())

    payload: dict[str, Any] = {
        "actionRequests": action_requests,
        "reviewConfigs": review_configs,
        "extensions": {
            "timeout": {
                "seconds": effective_timeout,
                "expiresAt": expires_at,
                "behavior": timeout_behavior,
            },
            "approval": {
                "requestId": request_id,
                "sessionKey": session_key,
                "batchSize": len(action_requests),
            },
            "displayMode": display_mode,
        },
    }
    if workspace_root:
        payload["extensions"]["workspaceRoot"] = workspace_root

    return payload, interrupt_indices
