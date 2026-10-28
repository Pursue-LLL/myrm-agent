"""Batch approval decision handling — applying the human's decisions to the pending tool calls.

[INPUT]
- agent.security (POS: security types, approval flow, audit, engine)
- agent.security.script_operand_verifier::compute_file_content_digest, extract_script_file_operand (POS: TOCTOU Defense verification)
- ._allow_always::try_add_to_allowlist (POS: remember an approved call as always-allowed unless a guard blocks it)
- .refusal::DenialCause, refusal_answer, rejection_cause (POS: the answer to a refused call, marked with who refused)

[OUTPUT]
- apply_approval_decisions: Apply user decisions to tool_calls and generate ToolMessages (blocks unsafe shell edits).

[POS]
The inbound half of batch approval — decision application; the interrupt payload is built by `_interrupt_payload`.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage

from myrm_agent_harness.agent.security.audit import record_decision
from myrm_agent_harness.agent.security.engine import extract_url_domains
from myrm_agent_harness.agent.security.types import SecurityConfig

from ._allow_always import try_add_to_allowlist
from .guidance_delivery import bounded_note
from .helpers import record_approval, record_denial, record_rejection
from .refusal import DenialCause, refusal_answer, rejection_cause

logger = logging.getLogger(__name__)

__all__ = ["apply_approval_decisions"]

_EDIT_REAPPROVAL_MESSAGE = (
    "Edited command requires new approval: modified shell commands with "
    "non-safe risk must be re-submitted by the agent."
)

_SHELL_EDIT_PERMISSION_TYPES = frozenset({"shell_exec", "code_interpreter"})


def _edited_shell_edit_block_reason(
    tool_name: str,
    permission_type: str,
    original_args: dict[str, object],
    edited_args: dict[str, object],
) -> str | None:
    """Return a rejection reason when an edited shell command must be re-approved."""
    from myrm_agent_harness.toolkits.code_execution.security.command_explainer.extract import (
        extract_shell_command_text,
        is_shell_approval_tool,
    )
    from myrm_agent_harness.toolkits.code_execution.security.risk_classifier import (
        CommandRiskLevel,
        classify_command_risk,
    )

    if permission_type not in _SHELL_EDIT_PERMISSION_TYPES:
        return None
    if not is_shell_approval_tool(tool_name):
        return None

    original_cmd = extract_shell_command_text(original_args)
    edited_cmd = extract_shell_command_text(edited_args)
    if not edited_cmd or original_cmd.strip() == edited_cmd.strip():
        return None
    if classify_command_risk(edited_cmd) == CommandRiskLevel.SAFE:
        return None
    return _EDIT_REAPPROVAL_MESSAGE


async def apply_approval_decisions(
    decisions: list[dict[str, Any]],
    last_ai_msg: AIMessage,
    auto_denied: list[tuple[int, ToolCall, str]],
    pending_approval: list[tuple[int, ToolCall, str, str, dict[str, Any] | None]],
    interrupt_indices: list[int],
    args_hashes: dict[int, str | None],
    config: SecurityConfig | None = None,
) -> tuple[list[ToolCall], list[ToolMessage], list[HumanMessage]]:
    """Apply user decisions to tool_calls and generate ToolMessages.

    When *config* is provided and ``domain_hitl_enabled`` is True, handles
    ``allowDomain`` extensions by adding approved domains to the session-scoped
    runtime allowlist.

    Returns: (revised_tool_calls, artificial_tool_messages, guidance_messages)
    """
    from myrm_agent_harness.agent.middlewares._session_context import (
        get_approval_session,
    )

    from ._batch_review import _get_runtime_domains

    session_key = get_approval_session()

    revised_tool_calls: list[ToolCall] = []
    artificial_tool_messages: list[ToolMessage] = []
    guidance_messages: list[HumanMessage] = []
    decision_idx = 0

    for idx, tool_call in enumerate(last_ai_msg.tool_calls):
        denied = next(((d_idx, tc, msg) for d_idx, tc, msg in auto_denied if d_idx == idx), None)
        if denied:
            _, _, error_msg = denied
            artificial_tool_messages.append(refusal_answer(tool_call, error_msg, DenialCause.POLICY))
            continue

        if idx in interrupt_indices:
            decision = decisions[decision_idx]
            decision_idx += 1

            _, _, permission_type, reason, extra_ctx = pending_approval[decision_idx - 1]
            tool_name = tool_call.get("name", "unknown")
            tool_call_id = tool_call.get("id", "")
            allowlist_tool_name = extra_ctx.get("ptc_tool_name_full", tool_name) if extra_ctx else tool_name

            decision_type = decision.get("type") or decision.get("decision") or "reject"
            extensions = decision.get("extensions", {})
            allow_always = decision.get("allow_always", extensions.get("allowAlways", False)) or decision.get(
                "allowAlways", False
            )
            allow_domain = decision.get("allow_domain", extensions.get("allowDomain", False))
            grant_directory = decision.get("grant_directory", extensions.get("grantDirectory", False))
            ttl_seconds = (
                decision.get("ttl_seconds")
                or decision.get("ttlSeconds")
                or extensions.get("ttlSeconds")
                or extensions.get("ttl_seconds")
            )
            guidance_text = decision.get("guidance", "").strip() if isinstance(decision.get("guidance"), str) else ""

            logger.info(
                "[APPROVAL] Tool %s decision: type=%s, allow_always=%s, allow_domain=%s, grant_directory=%s, ttl_seconds=%s",
                tool_name,
                decision_type,
                allow_always,
                allow_domain,
                grant_directory,
                ttl_seconds,
            )

            if decision_type == "approve":
                expected_digest = extra_ctx.get("action_digest") if extra_ctx else None
                if expected_digest:
                    from myrm_agent_harness.core.security.spend_governance import (
                        verify_action_digest,
                    )

                    user_digest = str(
                        decision.get("action_digest")
                        or decision.get("actionDigest")
                        or extensions.get("actionDigest")
                        or extensions.get("action_digest")
                        or ""
                    ).strip()
                    if not verify_action_digest(tool_name, tool_call.get("args", {}), user_digest):
                        logger.warning(
                            "[APPROVAL] Tool %s: action digest mismatch (expected=%s, received=%s)",
                            tool_name,
                            expected_digest,
                            user_digest,
                        )
                        record_decision(
                            tool_name,
                            "DIGEST_MISMATCH_REJECT",
                            "Financial action digest mismatch or missing: parameter tampering prevented",
                        )
                        hint = record_denial(tool_name, session_key)
                        artificial_tool_messages.append(
                            refusal_answer(
                                tool_call,
                                f"Security Blocked: Financial action digest verification failed. "
                                f"Expected '{expected_digest[:16]}...', received '{user_digest[:16] if user_digest else 'none'}...'. "
                                f"Execution aborted to prevent parameter tampering.{hint}",
                                DenialCause.POLICY,
                            )
                        )
                        continue

                expected_script_hash = extra_ctx.get("script_operand_hash") if extra_ctx else None
                script_path = extra_ctx.get("script_operand_path") if extra_ctx else None
                if expected_script_hash and script_path:
                    from myrm_agent_harness.agent.security.script_operand_verifier import (
                        verify_script_operand_integrity,
                    )

                    is_valid, drift_reason = verify_script_operand_integrity(expected_script_hash, script_path)
                    if not is_valid:
                        logger.warning(
                            "[APPROVAL] Tool %s script operand drift blocked: %s",
                            tool_name,
                            drift_reason,
                        )
                        record_decision(
                            tool_name,
                            "SCRIPT_OPERAND_DRIFT_REJECT",
                            drift_reason or "Approved script content modified before execution",
                        )
                        hint = record_denial(tool_name, session_key)
                        artificial_tool_messages.append(
                            refusal_answer(
                                tool_call,
                                f"Security Blocked: {drift_reason or 'Approved script content was modified before execution (TOCTOU detected)'}. "
                                f"Execution aborted to prevent unreviewed code from running.{hint}",
                                DenialCause.POLICY,
                            )
                        )
                        continue

                # ApprovedScriptsChangePrevention: generic script file content integrity check
                if extra_ctx and extra_ctx.get("script_content_hash"):
                    from myrm_agent_harness.core.security.spend_governance import (
                        verify_script_file_integrity,
                    )

                    exp_script_hash = str(extra_ctx.get("script_content_hash"))
                    target_script_path = str(extra_ctx.get("script_target") or "")
                    is_script_valid, script_fail_reason = verify_script_file_integrity(
                        target_script_path, exp_script_hash
                    )
                    if not is_script_valid:
                        logger.warning(
                            "[SCRIPT_INTEGRITY] TOCTOU script alteration detected on %s: %s",
                            tool_name,
                            script_fail_reason,
                        )
                        record_decision(
                            tool_name,
                            "SCRIPT_INTEGRITY_REJECT",
                            script_fail_reason,
                        )
                        hint = record_denial(tool_name, session_key)
                        artificial_tool_messages.append(
                            refusal_answer(
                                tool_call, f"Security Blocked: {script_fail_reason}{hint}", DenialCause.POLICY
                            )
                        )
                        continue

                if extra_ctx and extra_ctx.get("is_spend"):
                    raw_args = tool_call.get("args")
                    if isinstance(raw_args, dict) and "idempotency_key" not in raw_args:
                        raw_args["idempotency_key"] = f"myrm_tx_{uuid.uuid4().hex[:16]}"

                record_decision(tool_name, "USER_APPROVED", reason)
                record_approval(session_key)

                from myrm_agent_harness.agent.middlewares._session_context import (
                    get_workspace_root,
                )
                from myrm_agent_harness.agent.security.session_access import (
                    PATH_WRITE_PERMISSION_TYPES,
                    grant_directories_for_call,
                    grant_paths_once,
                )
                from myrm_agent_harness.agent.security.types import _default_path_policy

                call_args: dict[str, object] = tool_call.get("args", {})
                path_policy = config.path_policy if config else _default_path_policy()
                grant_workspace = get_workspace_root() or None
                grant_writable = permission_type in PATH_WRITE_PERMISSION_TYPES
                # Approving the call opens the files it names for that call alone, as the card says; the
                # "also grant folder access" choice is what keeps their folders for the session.
                for opened_path in grant_paths_once(
                    call_args, policy=path_policy, workspace_root=grant_workspace, writable=grant_writable
                ):
                    record_decision(tool_name, "PATH_OPENED_ONCE", f"path: {opened_path}")
                if grant_directory:
                    for granted_path in grant_directories_for_call(
                        call_args, policy=path_policy, workspace_root=grant_workspace, writable=grant_writable
                    ):
                        record_decision(tool_name, "DIRECTORY_GRANTED", f"path: {granted_path}")

                if allow_domain and config and config.domain_hitl_enabled:
                    tool_input: dict[str, object] = tool_call.get("args", {})
                    domains = extract_url_domains(permission_type, tool_input)
                    if domains:
                        runtime_domains = _get_runtime_domains()
                        for domain in domains:
                            runtime_domains.add(domain)
                        logger.warning(
                            "[DOMAIN_HITL] User approved domain(s) %s for session",
                            domains,
                        )
                        record_decision(tool_name, "DOMAIN_APPROVED", f"domains: {domains}")

                await try_add_to_allowlist(
                    tool_call,
                    extra_ctx,
                    allow_always,
                    permission_type,
                    allowlist_tool_name,
                    idx,
                    args_hashes,
                    ttl_seconds=ttl_seconds,
                )

                revised_tool_calls.append(tool_call)

            elif decision_type == "edit":
                edited_args = decision.get("args")

                edit_applied = False
                if edited_args is not None:
                    raw_original_args = tool_call.get("args", {})
                    original_args = dict(raw_original_args) if isinstance(raw_original_args, dict) else {}
                    normalized_edited_args = dict(edited_args) if isinstance(edited_args, dict) else {}
                    edit_block_reason = _edited_shell_edit_block_reason(
                        tool_name,
                        permission_type,
                        original_args,
                        normalized_edited_args,
                    )
                    if edit_block_reason is not None:
                        logger.warning(
                            "[APPROVAL] Tool %s: edited shell command blocked",
                            tool_name,
                        )
                        record_decision(tool_name, "USER_EDIT_REJECTED", edit_block_reason)
                        hint = record_denial(tool_name, session_key)
                        artificial_tool_messages.append(
                            refusal_answer(tool_call, f"{edit_block_reason}{hint}", DenialCause.POLICY)
                        )
                    else:
                        logger.warning("[APPROVAL] Tool %s: user edited args", tool_name)
                        record_decision(tool_name, "USER_EDITED", reason)
                        revised_tool_calls.append(
                            ToolCall(
                                type="tool_call",
                                name=tool_call.get("name", "unknown"),
                                args=normalized_edited_args,
                                id=tool_call_id,
                            )
                        )
                        edit_applied = True
                else:
                    record_decision(tool_name, "USER_EDITED", reason)
                    revised_tool_calls.append(tool_call)
                    edit_applied = True

                if edit_applied:
                    record_approval(session_key)
                    await try_add_to_allowlist(
                        tool_call,
                        extra_ctx,
                        allow_always,
                        permission_type,
                        allowlist_tool_name,
                        idx,
                        args_hashes,
                        ttl_seconds=ttl_seconds,
                    )

            else:
                feedback, content = record_rejection(decision, tool_name, session_key)
                logger.warning("[SECURITY] Tool %s REJECTED by user: %s", tool_name, feedback)
                record_decision(tool_name, "USER_REJECTED", feedback)
                artificial_tool_messages.append(refusal_answer(tool_call, content, rejection_cause(decision)))

            if guidance_text:
                logger.info(
                    "[APPROVAL] Tool %s: user provided guidance: %s",
                    tool_name,
                    guidance_text[:100],
                )
                guidance_messages.append(
                    HumanMessage(
                        content=f"[User Guidance during approval of {tool_name}]: {bounded_note(guidance_text)}",
                        additional_kwargs={"approval_guidance": True},
                    )
                )
        else:
            revised_tool_calls.append(tool_call)

    return revised_tool_calls, artificial_tool_messages, guidance_messages
