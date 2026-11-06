"""Batch Processor for Agent Security Approvals.

Decides, for each tool call of a model turn, whether it runs, is refused or waits for the user.

[INPUT]
- agent.security::engine, checks, audit, approval_flow, command_allowlist_pattern, managed_policy_gates, path_security, ptc_verifier, script_operand_verifier, tool_registry, types, guards.{skill_approval_hook, taint_tracker, untrusted_ingress_fence}, workspace_trust.{context, gate, types} (POS: The layered security stack this processor orchestrates: permission engine, path and taint checks, allowlist, managed-policy and workspace-trust gates.)
- core.security::readonly_research_sandbox, device_policy, spend_governance, remote_ops_ledger (POS: Foundation security primitives: read-only lease check, batch risk, spend rules, recovery hints.)
- toolkits.code_execution.security::ast_parser, risk_classifier, workspace_snapshot; toolkits.computer_use::safety (POS: Shell AST and risk classification, pre-destructive snapshots, desktop control guardrails.)
- agent.middlewares::_session_context; ._batch_review, ._batch_decisions, ._interrupt_payload, ._cron_policy::resolve_cron_ask, .denial_diagnostic_bridge::build_auto_review_denial_message, .helpers (POS: Shared middleware ContextVars, LLM review, interrupt payloads, cron settlement, the refusal text the model reads, denial tracking.)

[OUTPUT]
- register_security_reviewer, reset_runtime_domains: reviewer registration and the per-session runtime domain reset
- evaluate_tool_batch: classify every tool call into approved, denied or pending
- build_interrupt_payload, apply_approval_decisions: the approval interrupt payload and the user's decisions applied back
- is_yolo_mode_active, operator_as_key_deny_message: the YOLO state check and the refusal for a desktop vision key action naming a lone printable operator

[POS]
Orchestrates allowlist, YOLO and auto mode, path and taint checks, the read-only lease, cron declarations and the LLM security review into one verdict per call. Called by the approval middleware.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.tool_registry import (
    resolve_permission_type,
)
from myrm_agent_harness.agent.security.types import (
    RecentToolCall,
    SecurityConfig,
)

from .._batch_decisions import apply_approval_decisions
from .._batch_review import (
    _evaluate_skill_hooks_for_tool,
    _get_runtime_domains,
    _run_llm_review,
    _truncate_tool_args,
    register_security_reviewer,
    reset_runtime_domains,
)
from .._interrupt_payload import build_interrupt_payload
from .decide import evaluate_calls
from .yolo import _evaluate_yolo_batch, operator_as_key_deny_message

__all__ = [
    "_evaluate_skill_hooks_for_tool",
    "_get_runtime_domains",
    "_run_llm_review",
    "_truncate_tool_args",
    "apply_approval_decisions",
    "build_interrupt_payload",
    "evaluate_tool_batch",
    "is_yolo_mode_active",
    "operator_as_key_deny_message",
    "register_security_reviewer",
    "reset_runtime_domains",
]

logger = logging.getLogger(__name__)

def is_yolo_mode_active(config: SecurityConfig, *, session_key: str = "") -> bool:
    """Return True when YOLO is enabled and optional timeout has not expired."""
    if not config.yolo_mode_enabled:
        return False
    if config.yolo_mode_timeout and config.yolo_mode_enabled_at is not None:
        elapsed = time.time() - config.yolo_mode_enabled_at
        if elapsed > config.yolo_mode_timeout:
            if session_key:
                logger.warning(
                    "[YOLO] YOLO mode expired after %ds (session: %s)",
                    config.yolo_mode_timeout,
                    session_key,
                )
            return False
    return True


async def evaluate_tool_batch(
    tool_calls: list[ToolCall],
    config: SecurityConfig,
    is_cron: bool,
    workspace_root: str | None,
    session_key: str,
    args_hashes: dict[int, str | None],
    intent_context: str | None = None,
    recent_tool_calls: tuple[RecentToolCall, ...] = (),
    taint_labels: frozenset[str] | None = None,
    *,
    is_interactive: bool = True,
) -> tuple[
    list[tuple[int, ToolCall]],
    list[tuple[int, ToolCall, str]],
    list[tuple[int, ToolCall, str, str, dict[str, Any] | None]],
]:
    """Evaluate all tool calls and classify them into approved/denied/pending.

    Returns: (auto_approved, auto_denied, pending_approval)
    """
    auto_approved: list[tuple[int, ToolCall]] = []
    auto_denied: list[tuple[int, ToolCall, str]] = []
    pending_approval: list[tuple[int, ToolCall, str, str, dict[str, Any] | None]] = []

    from myrm_agent_harness.agent.middlewares._session_context import (
        get_agent_primary_model_slug,
        get_managed_approval_policy,
    )
    from myrm_agent_harness.agent.security.managed_policy_gates import (
        effective_auto_mode_enabled,
        yolo_allowed_for_model,
    )
    from myrm_agent_harness.agent.security.managed_policy_gates import (
        honor_allowlist as map_honor_allowlist,
    )

    map_policy = get_managed_approval_policy()
    agent_primary_model = get_agent_primary_model_slug()
    auto_mode_enabled = effective_auto_mode_enabled(config, map_policy, agent_primary_model)

    if is_yolo_mode_active(config, session_key=session_key) and yolo_allowed_for_model(map_policy, agent_primary_model):
        return await _evaluate_yolo_batch(
            tool_calls,
            config,
            workspace_root=workspace_root,
            session_key=session_key,
        )

    from myrm_agent_harness.core.security.device_policy import evaluate_batch_risk

    batch_assessment = evaluate_batch_risk(
        tool_calls,
        permission_resolver=resolve_permission_type,
    )

    return await evaluate_calls(
        tool_calls=tool_calls,
        config=config,
        is_cron=is_cron,
        workspace_root=workspace_root,
        session_key=session_key,
        args_hashes=args_hashes,
        intent_context=intent_context,
        recent_tool_calls=recent_tool_calls,
        taint_labels=taint_labels,
        is_interactive=is_interactive,
        auto_mode_enabled=auto_mode_enabled,
        map_policy=map_policy,
        map_honor_allowlist=map_honor_allowlist,
        agent_primary_model=agent_primary_model,
        batch_assessment=batch_assessment,
        auto_approved=auto_approved,
        auto_denied=auto_denied,
        pending_approval=pending_approval,
    )
